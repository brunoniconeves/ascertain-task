from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_list_patient_notes_default_sort_desc_and_cursor(client: TestClient) -> None:
    patient_id = create_patient(client=client, name="Eve Example", date_of_birth="1990-01-01")

    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for i in range(3):
        resp = client.post(
            f"/patients/{patient_id}/notes",
            json={"taken_at": (base + timedelta(minutes=i)).isoformat(), "content_text": f"n{i}"},
        )
        assert resp.status_code == 201, resp.text

    resp1 = client.get(f"/patients/{patient_id}/notes?limit=2")
    assert resp1.status_code == 200, resp1.text
    page1 = resp1.json()
    assert page1["limit"] == 2
    assert len(page1["items"]) == 2
    assert page1["items"][0]["content_text"] == "n2"
    assert page1["items"][1]["content_text"] == "n1"
    assert page1["next_cursor"] is not None

    resp2 = client.get(f"/patients/{patient_id}/notes?limit=2&cursor={page1['next_cursor']}")
    assert resp2.status_code == 200, resp2.text
    page2 = resp2.json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["content_text"] == "n0"


def test_delete_patient_note_soft_deletes_and_cleans_up_file(client: TestClient, tmp_path) -> None:
    base_dir = tmp_path / "data" / "notes"
    os.environ["LOCAL_STORAGE_BASE_PATH"] = str(base_dir)
    from app.core.settings import get_settings

    get_settings.cache_clear()

    patient_id = create_patient(client=client, name="Frank Example", date_of_birth="1990-01-01")

    taken_at = datetime.now(timezone.utc).isoformat()
    create = client.post(
        f"/patients/{patient_id}/notes",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"taken_at": taken_at},
    )
    assert create.status_code == 201, create.text
    note_id = create.json()["id"]

    # Ensure file exists under patient/note directory.
    note_dir = base_dir / patient_id / note_id
    assert note_dir.exists()
    assert any(p.is_file() for p in note_dir.rglob("*"))

    delete = client.delete(f"/patients/{patient_id}/notes/{note_id}")
    assert delete.status_code == 204, delete.text

    # After delete, note should not appear in list and file should be removed.
    listed = client.get(f"/patients/{patient_id}/notes")
    assert listed.status_code == 200, listed.text
    ids = [n["id"] for n in listed.json()["items"]]
    assert note_id not in ids

    assert not any(p.is_file() for p in note_dir.rglob("*"))


def test_list_patient_notes_includes_has_structured_data_flag_but_not_payload(
    client: TestClient,
) -> None:
    patient_id = create_patient(client=client, name="List Structured Flag", date_of_birth="1990-01-01")
    taken_at = datetime.now(timezone.utc).isoformat()

    # Create a SOAP note so derived structured data is persisted at write time.
    soap_text = "S: subj\nO: obj\nA: assess\nP: plan"
    created = client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": taken_at, "note_type": "soap", "content_text": soap_text},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    listed = client.get(f"/patients/{patient_id}/notes?limit=10")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(i["id"] == note_id for i in items)

    item = next(i for i in items if i["id"] == note_id)
    assert item["has_structured_data"] is True
    assert "structured_data" not in item

