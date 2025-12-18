from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def _sqlite_path_from_database_url() -> str:
    url = os.environ["DATABASE_URL"]
    prefix = "sqlite+aiosqlite:///"
    assert url.startswith(prefix)
    return url[len(prefix) :]


def _fetch_structured_payload(*, note_id: str) -> dict:
    db_path = _sqlite_path_from_database_url()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        # SQLite representation of UUIDs depends on SQLAlchemy type/dialect, so we
        # scan and normalize to compare against the API string UUID.
        cur.execute("SELECT note_id, data FROM patient_note_structured")
        rows = cur.fetchall()
        assert rows, "expected derived structured row(s) to be persisted"

        for note_id_db, data in rows:
            try:
                if isinstance(note_id_db, bytes):
                    normalized = str(uuid.UUID(bytes=note_id_db))
                else:
                    s = str(note_id_db)
                    # Some dialects store UUID as 32-char hex without dashes.
                    normalized = str(uuid.UUID(hex=s)) if len(s) == 32 else str(uuid.UUID(s))
            except Exception:  # noqa: BLE001
                continue

            if normalized == note_id:
                return json.loads(data) if isinstance(data, str) else data

        raise AssertionError("expected derived structured row to be persisted for note_id")
    finally:
        con.close()


def test_create_patient_note_inline_soap_persists_structured_data(client: TestClient) -> None:
    patient_id = create_patient(client=client, name="Soap Inline", date_of_birth="1990-01-01")
    taken_at = datetime.now(UTC).isoformat()

    soap_text = "S: subj\nO: obj\nA: assess\nP: plan"
    resp = client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": taken_at, "note_type": "soap", "content_text": soap_text},
    )
    assert resp.status_code == 201, resp.text

    note_id = resp.json()["id"]
    payload = _fetch_structured_payload(note_id=note_id)

    assert payload["schema"] == "soap_v1"
    assert payload["parsed_from"] == "text"
    assert payload["parser_version"] == "v1"
    assert payload["confidence"] == "high"
    assert payload["sections"]["subjective"] == "subj\n"
    assert payload["sections"]["objective"] == "obj\n"
    assert payload["sections"]["assessment"] == "assess\n"
    assert payload["sections"]["plan"] == "plan"


def test_create_patient_note_file_soap_persists_structured_data(
    client: TestClient, tmp_path
) -> None:
    os.environ["LOCAL_STORAGE_BASE_PATH"] = str(tmp_path / "data" / "notes")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    patient_id = create_patient(client=client, name="Soap File", date_of_birth="1990-01-01")
    taken_at = datetime.now(UTC).isoformat()

    soap_bytes = b"S: subj\nO: obj\nA: assess\nP: plan"
    resp = client.post(
        f"/patients/{patient_id}/notes",
        files={"file": ("note.txt", soap_bytes, "text/plain")},
        data={"taken_at": taken_at, "note_type": "soap"},
    )
    assert resp.status_code == 201, resp.text

    note_id = resp.json()["id"]
    payload = _fetch_structured_payload(note_id=note_id)
    assert payload["schema"] == "soap_v1"
    assert payload["confidence"] == "high"


def test_create_patient_note_inline_soap_missing_sections_is_partial_but_not_rejected(
    client: TestClient,
) -> None:
    patient_id = create_patient(client=client, name="Soap Partial", date_of_birth="1990-01-01")
    taken_at = datetime.now(UTC).isoformat()

    soap_text = "S: subj\nO: obj\nA: assess"
    resp = client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": taken_at, "note_type": "soap", "content_text": soap_text},
    )
    assert resp.status_code == 201, resp.text

    note_id = resp.json()["id"]
    payload = _fetch_structured_payload(note_id=note_id)
    assert payload["confidence"] == "partial"
    assert payload["sections"]["plan"] is None
