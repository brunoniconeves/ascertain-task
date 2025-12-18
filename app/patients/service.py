from __future__ import annotations

import base64
import secrets
import uuid
from datetime import date

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.domain.exceptions import BusinessValidationError
from app.patients.cursor_pagination import (
    decode_patient_cursor,
    encode_patient_cursor,
    format_cursor_value,
    parse_cursor_value,
)
from app.patients.models import Patient


def _apply_patient_filters(*, stmt: Select, q: str | None) -> Select:
    if not q:
        return stmt

    normalized = q.strip().lower()
    if not normalized:
        return stmt

    return stmt.where(func.lower(Patient.name).contains(normalized))


def _apply_patient_sorting(
    *,
    stmt: Select[tuple[Patient]],
    sort: str | None,
    order: str,
) -> Select[tuple[Patient]]:
    sort_map = {
        "name": Patient.name,
        "date_of_birth": Patient.date_of_birth,
        "created_at": Patient.created_at,
    }
    sort_col = sort_map.get(sort or "", Patient.created_at)
    if order == "desc":
        return stmt.order_by(sort_col.desc(), Patient.id.desc())
    return stmt.order_by(sort_col.asc(), Patient.id.asc())


def _apply_patient_cursor(
    *,
    stmt: Select[tuple[Patient]],
    sort: str,
    order: str,
    cursor: str | None,
    name: str | None,
) -> Select[tuple[Patient]]:
    if not cursor:
        return stmt

    decoded = decode_patient_cursor(cursor=cursor, sort=sort, order=order, name=name)
    sort_map = {
        "name": Patient.name,
        "date_of_birth": Patient.date_of_birth,
        "created_at": Patient.created_at,
    }
    sort_col = sort_map.get(sort or "", Patient.created_at)
    last_value = parse_cursor_value(sort=sort, raw=decoded.last_value)
    last_id = decoded.last_id

    if order == "desc":
        return stmt.where(
            or_(
                sort_col < last_value,
                and_(sort_col == last_value, Patient.id < last_id),
            )
        )
    return stmt.where(
        or_(
            sort_col > last_value,
            and_(sort_col == last_value, Patient.id > last_id),
        )
    )


async def list_patients(
    *,
    session: AsyncSession,
    limit: int,
    cursor: str | None,
    name: str | None,
    sort: str | None,
    order: str,
) -> tuple[list[Patient], str | None]:
    sort = sort or "created_at"
    items_stmt = select(Patient)
    items_stmt = _apply_patient_filters(stmt=items_stmt, q=name)
    items_stmt = _apply_patient_sorting(stmt=items_stmt, sort=sort, order=order)
    items_stmt = _apply_patient_cursor(
        stmt=items_stmt, sort=sort, order=order, cursor=cursor, name=name
    )
    items_stmt = items_stmt.limit(limit + 1)

    fetched = (await session.execute(items_stmt)).scalars().all()
    has_more = len(fetched) > limit
    items = fetched[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        last_value = format_cursor_value(sort=sort, value=getattr(last, sort))
        next_cursor = encode_patient_cursor(
            sort=sort,
            order=order,
            name=name,
            last_id=last.id,
            last_value=last_value,
        )

    return items, next_cursor


async def get_patient(*, session: AsyncSession, patient_id: uuid.UUID) -> Patient | None:
    return await session.get(Patient, patient_id)


def _normalize_mrn(*, mrn: str) -> str:
    # Normalize whitespace; do not alter case (caller may depend on exact casing).
    normalized = mrn.strip()
    if not normalized:
        raise BusinessValidationError("MRN must not be empty.")
    if len(normalized) > 50:
        raise BusinessValidationError("MRN must be 50 characters or fewer.")
    # Keep character set conservative. We avoid spaces and punctuation to reduce downstream issues.
    # This does NOT encode PHI; it's only format validation.
    for ch in normalized:
        if not (ch.isalnum() or ch == "-"):
            raise BusinessValidationError("MRN contains invalid characters.")
    return normalized


def _generate_mrn(*, prefix: str) -> str:
    """
    Generate an opaque MRN with deterministic *format*.

    Strategy:
    - Prefix (default: "MRN-") + 13 chars of Base32 (RFC4648) derived from 64 bits of randomness.
    - Does not encode PHI (no DOB/name hashing).
    - Collision-safe in practice; uniqueness is enforced by a DB unique index, and we retry on
      conflict.
    """

    token = base64.b32encode(secrets.token_bytes(8)).decode("ascii").rstrip("=")  # 13 chars
    return f"{prefix}{token}"


async def _mrn_exists(*, session: AsyncSession, mrn: str) -> bool:
    stmt = select(Patient.id).where(Patient.mrn == mrn).limit(1)
    row = (await session.execute(stmt)).first()
    return row is not None


async def _generate_unique_mrn(*, session: AsyncSession) -> str:
    settings = get_settings()
    prefix = settings.patient_mrn_prefix
    # Retry loop is a belt-and-suspenders approach: DB uniqueness is the source of truth.
    for _ in range(5):
        candidate = _generate_mrn(prefix=prefix)
        if not await _mrn_exists(session=session, mrn=candidate):
            return candidate
    # Extremely unlikely unless DB is unhealthy or uniqueness checks are racing heavily.
    raise BusinessValidationError("Unable to generate MRN at this time.")


async def create_patient(
    *,
    session: AsyncSession,
    name: str,
    date_of_birth: date,
    mrn: str | None = None,
) -> Patient:
    _validate_date_of_birth(date_of_birth=date_of_birth)

    settings = get_settings()
    normalized_mrn: str | None = None
    if mrn is not None:
        normalized_mrn = _normalize_mrn(mrn=mrn)
        if await _mrn_exists(session=session, mrn=normalized_mrn):
            # Do not include MRN in the message (PHI-adjacent).
            raise BusinessValidationError("MRN is already in use.")
    else:
        if not settings.patient_mrn_auto_generate:
            # DB enforces NOT NULL; keep this as a business error rather than a DB error.
            raise BusinessValidationError("MRN is required.")
        normalized_mrn = await _generate_unique_mrn(session=session)

    # If MRN is auto-generated, a rare race/collision can still happen at commit.
    # We retry generation on IntegrityError without exposing the MRN.
    for _attempt in range(5):
        patient = Patient(name=name, date_of_birth=date_of_birth, mrn=normalized_mrn)
        session.add(patient)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if mrn is not None:
                # Client-provided MRN conflict (or other constraint issue). Don't leak details.
                raise BusinessValidationError("MRN is already in use.") from None
            if not settings.patient_mrn_auto_generate:
                raise BusinessValidationError(
                    "Patient could not be created due to a data conflict."
                ) from None
            # Regenerate and retry.
            normalized_mrn = await _generate_unique_mrn(session=session)
            continue

        await session.refresh(patient)
        return patient

    raise BusinessValidationError("Unable to generate MRN at this time.")


async def update_patient(
    *,
    session: AsyncSession,
    patient: Patient,
    name: str | None,
    date_of_birth: date | None,
    mrn: str | None = None,
) -> Patient:
    if mrn is not None:
        # MRN is immutable via API to preserve clinical identifier integrity.
        raise BusinessValidationError("MRN cannot be updated.")

    if name is not None:
        patient.name = name
    if date_of_birth is not None:
        _validate_date_of_birth(date_of_birth=date_of_birth)
        patient.date_of_birth = date_of_birth

    await session.commit()
    await session.refresh(patient)
    return patient


async def delete_patient(*, session: AsyncSession, patient: Patient) -> None:
    await session.delete(patient)
    await session.commit()


def _validate_date_of_birth(*, date_of_birth: date) -> None:
    if date_of_birth > date.today():
        raise BusinessValidationError("date_of_birth must be today or in the past.")
