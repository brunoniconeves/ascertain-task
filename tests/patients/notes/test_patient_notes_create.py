from __future__ import annotations

from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_create_patient_note_inline_text_happy_path(client: TestClient) -> None:
    patient_id = create_patient(client=client, name="Alice Example", date_of_birth="1990-01-01")

    taken_at = datetime.now(UTC).isoformat()
    resp = client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": taken_at, "note_type": "progress", "content_text": "Patient is stable."},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["patient_id"] == patient_id
    assert data["note_type"] == "progress"
    assert data["content_text"] == "Patient is stable."
    assert data["has_file"] is False


def test_create_patient_note_rejects_future_taken_at(client: TestClient) -> None:
    patient_id = create_patient(client=client, name="Bob Example", date_of_birth="1991-01-01")

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    resp = client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": future, "content_text": "Future note"},
    )
    assert resp.status_code == 400, resp.text
