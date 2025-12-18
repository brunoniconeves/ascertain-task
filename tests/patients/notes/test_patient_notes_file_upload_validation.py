from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_create_patient_note_file_rejects_unsupported_mime_type(client: TestClient, tmp_path) -> None:
    os.environ["LOCAL_STORAGE_BASE_PATH"] = str(tmp_path / "data" / "notes")
    from app.core.settings import get_settings

    get_settings.cache_clear()

    patient_id = create_patient(client=client, name="Carol Example", date_of_birth="1992-01-01")

    taken_at = datetime.now(timezone.utc).isoformat()
    resp = client.post(
        f"/patients/{patient_id}/notes",
        files={"file": ("x.bin", b"binary", "application/octet-stream")},
        data={"taken_at": taken_at},
    )
    assert resp.status_code == 415, resp.text


def test_create_patient_note_file_upload_happy_path(client: TestClient, tmp_path) -> None:
    base_dir = tmp_path / "data" / "notes"
    os.environ["LOCAL_STORAGE_BASE_PATH"] = str(base_dir)
    from app.core.settings import get_settings

    get_settings.cache_clear()

    patient_id = create_patient(client=client, name="Dana Example", date_of_birth="1993-01-01")
    taken_at = datetime.now(timezone.utc).isoformat()

    resp = client.post(
        f"/patients/{patient_id}/notes",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"taken_at": taken_at, "note_type": "discharge"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["patient_id"] == patient_id
    assert data["content_text"] is None
    assert data["content_mime_type"] == "text/plain"
    assert data["has_file"] is True

    # API must not expose filesystem paths; validate file exists by scanning under base_dir.
    note_id = data["id"]
    note_dir = base_dir / patient_id / note_id
    assert note_dir.exists()
    assert any(p.is_file() for p in note_dir.rglob("*"))


def test_create_patient_note_pdf_sniffs_content_type_when_client_sends_text_plain(
    client: TestClient, tmp_path
) -> None:
    base_dir = tmp_path / "data" / "notes"
    os.environ["LOCAL_STORAGE_BASE_PATH"] = str(base_dir)
    from app.core.settings import get_settings

    get_settings.cache_clear()

    patient_id = create_patient(client=client, name="PDF Example", date_of_birth="1993-01-01")
    taken_at = datetime.now(timezone.utc).isoformat()

    # Some clients mislabel PDFs as text/plain; we should sniff %PDF- and store application/pdf.
    fake_pdf = b"%PDF-1.7\n%fake\n"
    resp = client.post(
        f"/patients/{patient_id}/notes",
        files={"file": ("test.pdf", fake_pdf, "text/plain")},
        data={"taken_at": taken_at},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["content_mime_type"] == "application/pdf"


