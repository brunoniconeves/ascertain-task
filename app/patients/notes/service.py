from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import BusinessValidationError
from app.patients.models import Patient
from app.patients.notes.cursor_pagination import NoteCursor, decode_note_cursor, encode_note_cursor
from app.patients.notes.models import PatientNote, PatientNoteStructured
from app.patients.notes.soap_parser import parse_soap
from app.patients.notes.storage import StoredFile

logger = logging.getLogger("app.soap")


def _ensure_timezone_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        # Interpret naive timestamps as UTC for safety and consistency.
        return dt.replace(tzinfo=UTC)
    return dt


def _validate_taken_at_not_future(*, taken_at: datetime) -> None:
    taken_at = _ensure_timezone_aware(taken_at)
    if taken_at > datetime.now(UTC):
        raise BusinessValidationError("taken_at must not be in the future.")


async def _maybe_parse_and_persist_soap(
    *,
    session: AsyncSession,
    note: PatientNote,
    raw_text: str | None,
) -> None:
    """
    Best-effort SOAP parsing + persistence of derived structured data.

    - Only runs when note.note_type == "soap" (case-insensitive).
    - Never raises to callers (source-of-truth note must be persisted regardless).
    - Never logs note content or other PHI; warnings include only non-PHI metadata.
    """

    if (note.note_type or "").strip().lower() != "soap":
        return

    if not raw_text:
        logger.warning("SOAP parse skipped: missing raw text (note_id=%s)", str(note.id))
        return

    try:
        parsed = parse_soap(raw_text)
    except Exception as exc:  # noqa: BLE001
        # Defensive: parse_soap should be pure/deterministic; never block note creation.
        logger.warning(
            "SOAP parse failed: parser raised (note_id=%s, error=%s)",
            str(note.id),
            exc.__class__.__name__,
        )
        return

    if parsed is None:
        logger.warning("SOAP parse failed: no SOAP markers found (note_id=%s)", str(note.id))
        return

    if parsed.confidence != "high":
        # Per requirements: log warning for incomplete parsing.
        logger.warning(
            "SOAP parse incomplete (note_id=%s, confidence=%s)", str(note.id), parsed.confidence
        )

    payload = {
        "schema": parsed.schema,
        "parsed_from": parsed.parsed_from,
        "parser_version": parsed.parser_version,
        "confidence": parsed.confidence,
        "sections": parsed.sections,
    }

    try:
        row = PatientNoteStructured(
            id=uuid.uuid4(),
            note_id=note.id,
            schema=parsed.schema,
            parsed_from=parsed.parsed_from,
            parser_version=parsed.parser_version,
            confidence=parsed.confidence,
            data=payload,
        )
        session.add(row)
        await session.commit()
    except IntegrityError:
        # Deterministic + idempotent behavior: if the row already exists, do nothing.
        await session.rollback()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        logger.warning(
            "SOAP parse persistence failed (note_id=%s, error=%s)",
            str(note.id),
            exc.__class__.__name__,
        )


async def create_inline_patient_note(
    *,
    session: AsyncSession,
    patient: Patient,
    taken_at: datetime,
    note_type: str | None,
    content_text: str,
    content_mime_type: str | None,
) -> PatientNote:
    taken_at = _ensure_timezone_aware(taken_at)
    _validate_taken_at_not_future(taken_at=taken_at)

    note = PatientNote(
        id=uuid.uuid4(),
        patient_id=patient.id,
        taken_at=taken_at,
        note_type=note_type,
        content_text=content_text,
        content_mime_type=content_mime_type or "text/plain",
        file_path=None,
        file_size_bytes=None,
        checksum_sha256=None,
        deleted_at=None,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)

    # Best-effort derived parsing (non-authoritative, source-of-truth remains content_text).
    await _maybe_parse_and_persist_soap(session=session, note=note, raw_text=content_text)

    return note


async def create_file_patient_note(
    *,
    session: AsyncSession,
    patient: Patient,
    note_id: uuid.UUID,
    taken_at: datetime,
    note_type: str | None,
    content_mime_type: str,
    stored_file: StoredFile,
    raw_text_for_parsing: str | None,
) -> PatientNote:
    taken_at = _ensure_timezone_aware(taken_at)
    _validate_taken_at_not_future(taken_at=taken_at)

    note = PatientNote(
        id=note_id,
        patient_id=patient.id,
        taken_at=taken_at,
        note_type=note_type,
        content_text=None,
        content_mime_type=content_mime_type,
        file_path=stored_file.key,
        file_size_bytes=stored_file.size_bytes,
        checksum_sha256=stored_file.sha256_hex,
        deleted_at=None,
    )

    session.add(note)
    await session.commit()
    await session.refresh(note)

    # Best-effort derived parsing (non-authoritative, source-of-truth remains the file).
    await _maybe_parse_and_persist_soap(session=session, note=note, raw_text=raw_text_for_parsing)

    return note


def _apply_notes_cursor(
    *,
    stmt: Select[tuple[PatientNote]],
    patient_id: uuid.UUID,
    cursor: str | None,
) -> Select[tuple[PatientNote]]:
    if not cursor:
        return stmt

    decoded = decode_note_cursor(raw=cursor)
    if decoded.patient_id != patient_id:
        raise ValueError("Invalid cursor")

    # Default sort is taken_at DESC, tie-breaker id DESC.
    return stmt.where(
        or_(
            PatientNote.taken_at < decoded.last_taken_at,
            and_(PatientNote.taken_at == decoded.last_taken_at, PatientNote.id < decoded.last_id),
        )
    )


async def list_patient_notes(
    *,
    session: AsyncSession,
    patient_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> tuple[list[PatientNote], str | None]:
    stmt = select(PatientNote).where(
        PatientNote.patient_id == patient_id, PatientNote.deleted_at.is_(None)
    )
    stmt = stmt.order_by(PatientNote.taken_at.desc(), PatientNote.id.desc())
    stmt = _apply_notes_cursor(stmt=stmt, patient_id=patient_id, cursor=cursor)
    stmt = stmt.limit(limit + 1)

    fetched = (await session.execute(stmt)).scalars().all()
    has_more = len(fetched) > limit
    items = fetched[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_note_cursor(
            cursor=NoteCursor(
                patient_id=patient_id,
                last_taken_at=last.taken_at,
                last_id=last.id,
            )
        )

    return items, next_cursor


async def get_patient_note(
    *,
    session: AsyncSession,
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
) -> PatientNote | None:
    stmt = select(PatientNote).where(
        PatientNote.id == note_id,
        PatientNote.patient_id == patient_id,
        PatientNote.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalars().first()


async def soft_delete_patient_note(
    *,
    session: AsyncSession,
    note: PatientNote,
    deleted_at: datetime,
) -> None:
    note.deleted_at = deleted_at
    await session.commit()
