from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def create_patient(*, session: AsyncSession, name: str, date_of_birth: date) -> Patient:
    _validate_date_of_birth(date_of_birth=date_of_birth)

    patient = Patient(name=name, date_of_birth=date_of_birth)
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


async def update_patient(
    *,
    session: AsyncSession,
    patient: Patient,
    name: str | None,
    date_of_birth: date | None,
) -> Patient:
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
