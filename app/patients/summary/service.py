from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import get_settings
from app.patients.models import Patient
from app.patients.notes.models import PatientNote
from app.patients.service import get_patient
from app.patients.summary.prompt import build_patient_summary_prompts
from app.patients.summary.schemas import (
    PatientHeading,
    PatientSummaryOut,
    SummaryAudience,
    SummaryContent,
    SummaryVerbosity,
    _LLMSummaryJSON,
)


class LLMClient(Protocol):
    async def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class PatientSummaryLLMError(Exception):
    """Raised when the LLM fails or returns invalid output."""


def _calculate_age(*, date_of_birth: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - date_of_birth.year
    # If birthday hasn't occurred yet this year, subtract one year.
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return max(years, 0)


def _truncate_notes_for_prompt(
    *, notes: list[dict[str, Any]], max_prompt_chars: int
) -> list[dict[str, Any]]:
    """
    Soft-cap the prompt size by truncating note text fields while keeping metadata.

    Safety: when truncation occurs, we explicitly mark the note as truncated so the
    model does not infer missing content.
    """

    remaining = max_prompt_chars
    out: list[dict[str, Any]] = []

    for note in notes:
        n = dict(note)
        text = n.get("content_text")
        if isinstance(text, str) and text:
            if remaining <= 0:
                n["content_text"] = None
                n["content_truncated"] = True
            elif len(text) > remaining:
                n["content_text"] = text[:remaining] + "\n[TRUNCATED]"
                n["content_truncated"] = True
                remaining = 0
            else:
                remaining -= len(text)
        out.append(n)

    return out


class PatientSummaryService:
    def __init__(self, *, session: AsyncSession, llm_client: LLMClient):
        self._session = session
        self._llm = llm_client

    async def generate_summary(
        self,
        *,
        patient_id: uuid.UUID,
        audience: SummaryAudience,
        verbosity: SummaryVerbosity,
    ) -> PatientSummaryOut | None:
        patient: Patient | None = await get_patient(session=self._session, patient_id=patient_id)
        if patient is None:
            return None

        heading = PatientHeading(
            name=patient.name,
            age=_calculate_age(date_of_birth=patient.date_of_birth),
            mrn=None,  # MRN not currently stored in this codebase; keep nullable for forward-compat.
        )

        stmt = (
            select(PatientNote)
            .where(PatientNote.patient_id == patient_id, PatientNote.deleted_at.is_(None))
            .options(selectinload(PatientNote.structured))
            .order_by(PatientNote.taken_at.asc(), PatientNote.id.asc())
        )
        notes_rows = (await self._session.execute(stmt)).scalars().all()

        notes_for_prompt: list[dict[str, Any]] = []
        for n in notes_rows:
            notes_for_prompt.append(
                {
                    "id": str(n.id),
                    "taken_at": n.taken_at.isoformat(),
                    "note_type": n.note_type,
                    "has_file": bool(n.has_file),
                    # Only include fields that are already returned by the API.
                    "content_text": n.content_text,
                    "content_mime_type": n.content_mime_type,
                    "file_size_bytes": n.file_size_bytes,
                    "checksum_sha256": n.checksum_sha256,
                    "structured_data": n.structured_data,
                }
            )

        settings = get_settings()
        notes_for_prompt = _truncate_notes_for_prompt(
            notes=notes_for_prompt, max_prompt_chars=int(settings.openai_max_prompt_chars)
        )

        # Only send minimal patient context; avoid unnecessary PHI like full DOB.
        patient_context = {"age_years": heading.age, "mrn": heading.mrn}

        system_prompt, user_prompt = build_patient_summary_prompts(
            audience=audience,
            verbosity=verbosity,
            patient_context=patient_context,
            notes=notes_for_prompt,
        )

        try:
            llm_json = await self._llm.generate_json(
                system_prompt=system_prompt, user_prompt=user_prompt
            )
            parsed = _LLMSummaryJSON.model_validate(llm_json)
        except Exception as exc:  # noqa: BLE001
            raise PatientSummaryLLMError("LLM summary generation failed") from exc

        return PatientSummaryOut(
            patient_heading=heading,
            summary=SummaryContent(audience=audience, verbosity=verbosity, text=parsed.text),
        )
