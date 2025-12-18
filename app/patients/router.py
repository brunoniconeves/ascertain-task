from __future__ import annotations

import logging
import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.llm.deps import get_openai_client
from app.core.llm.openai_client import OpenAIError
from app.patients.notes.router import router as patient_notes_router
from app.patients.schemas import (
    PatientCreate,
    PatientListItemOut,
    PatientListOut,
    PatientOut,
    PatientSortField,
    PatientUpdate,
    SortOrder,
)
from app.patients.service import (
    create_patient,
    delete_patient,
    get_patient,
    list_patients,
    update_patient,
)
from app.patients.summary.schemas import PatientSummaryOut, SummaryAudience, SummaryVerbosity
from app.patients.summary.service import PatientSummaryLLMError, PatientSummaryService

router = APIRouter(prefix="/patients", tags=["patients"])
router.include_router(patient_notes_router)
logger = logging.getLogger("app.patient_summary")


def _validate_summary_params(
    *, audience: str, verbosity: str
) -> tuple[SummaryAudience, SummaryVerbosity]:
    allowed_audience = {"clinician", "family", "patient", "third_party"}
    allowed_verbosity = {"short", "medium", "long"}

    if audience not in allowed_audience:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audience. Supported values: clinician, family, patient, third_party.",
        )
    if verbosity not in allowed_verbosity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verbosity. Supported values: short, medium, long.",
        )

    # Cast is safe due to allowlist checks above.
    return cast(SummaryAudience, audience), cast(SummaryVerbosity, verbosity)


@router.get("", response_model=PatientListOut)
async def get_patients(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(
        default=None, description="Cursor for pagination (use `next_cursor` from previous response)"
    ),
    offset: int | None = Query(default=None, ge=0, include_in_schema=False),
    name: str | None = Query(
        default=None,
        min_length=1,
        description="Filter by name (case-insensitive substring match). Minimum length: 3.",
    ),
    q: str | None = Query(default=None, min_length=1, include_in_schema=False),
    sort: PatientSortField | None = Query(default=None),
    order: SortOrder = Query(default="asc"),
    session: AsyncSession = Depends(get_session),
) -> PatientListOut:
    # Backwards-compatible alias: `q` was the original param name.
    if name is None and q is not None:
        name = q

    if name is not None and len(name.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'name' must be at least 3 characters long.",
        )

    if offset is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="offset pagination is not supported; use cursor",
        )

    try:
        items, next_cursor = await list_patients(
            session=session, limit=limit, cursor=cursor, name=name, sort=sort, order=order
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    items_out = [PatientListItemOut.model_validate(p) for p in items]
    return PatientListOut(items=items_out, limit=limit, next_cursor=next_cursor)


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient_by_id(
    patient_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PatientOut:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.get("/{patient_id}/summary", response_model=PatientSummaryOut)
async def get_patient_summary(
    patient_id: uuid.UUID,
    request: Request,
    audience: str = Query(default="clinician"),
    verbosity: str = Query(default="medium"),
    session: AsyncSession = Depends(get_session),
    openai_client=Depends(get_openai_client),
) -> PatientSummaryOut:
    """
    Generate a read-only, non-persistent patient summary using an LLM.

    IMPORTANT (safety):
    - We do not store LLM output anywhere.
    - We do not log prompts or LLM outputs (may contain PHI).
    """

    aud, verb = _validate_summary_params(audience=audience, verbosity=verbosity)
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")

    if openai_client is None:
        logger.info(
            "Patient summary failed (LLM not configured)",
            extra={
                "request_id": request_id,
                "patient_id": str(patient_id),
                "audience": aud,
                "verbosity": verb,
                "success": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM service unavailable"
        )

    svc = PatientSummaryService(session=session, llm_client=openai_client)
    try:
        summary = await svc.generate_summary(patient_id=patient_id, audience=aud, verbosity=verb)
        if summary is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    except HTTPException:
        raise
    except (OpenAIError, PatientSummaryLLMError):
        logger.info(
            "Patient summary failed",
            extra={
                "request_id": request_id,
                "patient_id": str(patient_id),
                "audience": aud,
                "verbosity": verb,
                "success": False,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM service failed",
        ) from None

    logger.info(
        "Patient summary generated",
        extra={
            "request_id": request_id,
            "patient_id": str(patient_id),
            "audience": aud,
            "verbosity": verb,
            "success": True,
        },
    )
    return summary


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PatientOut)
async def create_patient_route(
    payload: PatientCreate,
    session: AsyncSession = Depends(get_session),
) -> PatientOut:
    patient = await create_patient(
        session=session,
        name=payload.name,
        date_of_birth=payload.date_of_birth,
        mrn=payload.mrn,
    )
    return patient


@router.put("/{patient_id}", response_model=PatientOut)
async def update_patient_by_id(
    patient_id: uuid.UUID,
    payload: PatientUpdate,
    session: AsyncSession = Depends(get_session),
) -> PatientOut:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    updated = await update_patient(
        session=session,
        patient=patient,
        name=payload.name,
        date_of_birth=payload.date_of_birth,
        mrn=payload.mrn,
    )
    return updated


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_patient_by_id(
    patient_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    await delete_patient(session=session, patient=patient)
    return None
