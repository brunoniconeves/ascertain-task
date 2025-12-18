"""Seed patient data for local development.

This script is designed to be safe to run multiple times:
- It only runs when APP_ENV=development
- It inserts rows only when the patients table is empty
"""

# ruff: noqa: I001
# pyright: reportMissingImports=false
from __future__ import annotations

import asyncio
import base64
import os
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.patients.models import Patient


def _mrn_for_seed_patient(*, patient_id: uuid.UUID) -> str:
    """
    Deterministic, opaque MRN for local dev seed data.

    Design:
    - Format is deterministic (MRN-<BASE32>).
    - Does NOT encode PHI (not derived from name/DOB); derived from the stable UUID instead.
    - Collision-safe for this dataset because patient UUIDs are unique.
    """

    token = base64.b32encode(patient_id.bytes).decode("ascii").rstrip("=")  # 26 chars
    return f"MRN-{token}"


def _seed_rows() -> list[dict]:
    """Return a deterministic set of patient seed rows."""
    # Deterministic UUIDs so even if the seed runs concurrently, the IDs are stable.
    ns = uuid.UUID("3b241101-e2bb-4255-8caf-4136c566a962")
    rows = [
        ("Ada Lovelace", date(1815, 12, 10)),
        ("Alan Turing", date(1912, 6, 23)),
        ("Grace Hopper", date(1906, 12, 9)),
        ("Katherine Johnson", date(1918, 8, 26)),
        ("Margaret Hamilton", date(1936, 8, 17)),
        ("Donald Knuth", date(1938, 1, 10)),
        ("Edsger Dijkstra", date(1930, 5, 11)),
        ("Barbara Liskov", date(1939, 11, 7)),
        ("Ken Thompson", date(1943, 2, 4)),
        ("Dennis Ritchie", date(1941, 9, 9)),
        ("Linus Torvalds", date(1969, 12, 28)),
        ("Tim Berners-Lee", date(1955, 6, 8)),
        ("Guido van Rossum", date(1956, 1, 31)),
        ("James Gosling", date(1955, 5, 19)),
        ("Bjarne Stroustrup", date(1950, 12, 30)),
    ]

    out: list[dict] = []
    for name, dob in rows:
        patient_id = uuid.uuid5(ns, name)
        out.append(
            {
                "id": patient_id,
                "name": name,
                "date_of_birth": dob,
                "mrn": _mrn_for_seed_patient(patient_id=patient_id),
            }
        )
    return out


async def seed_patients_if_empty(*, database_url: str) -> None:
    """Seed 15 patients if the patients table is empty."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        total = int((await session.execute(select(func.count()).select_from(Patient))).scalar_one())
        if total > 0:
            print(f"Seed skipped: patients table already has {total} row(s).")
            await engine.dispose()
            return

        patients = [Patient(**row) for row in _seed_rows()]
        session.add_all(patients)
        await session.commit()
        print(f"Seeded {len(patients)} patients.")

    await engine.dispose()


def main() -> None:
    """Entry point."""
    app_env = os.getenv("APP_ENV", "production").strip().lower()
    if app_env != "development":
        print(f"Seed skipped: APP_ENV={app_env!r} (seeding only runs in development).")
        return

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    asyncio.run(seed_patients_if_empty(database_url=database_url))


if __name__ == "__main__":
    main()
