"""Integration tests: patient CRUD lifecycle."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_patient_crud_lifecycle_happy_path(client: TestClient) -> None:
    """Create -> Get -> Update -> Delete -> 404."""
    patient_id = create_patient(client=client, name="Ada Lovelace", date_of_birth="1815-12-10")

    get_res = client.get(f"/patients/{patient_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == patient_id

    update_res = client.put(f"/patients/{patient_id}", json={"name": "Ada King"})
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Ada King"

    delete_res = client.delete(f"/patients/{patient_id}")
    assert delete_res.status_code == 204

    missing_res = client.get(f"/patients/{patient_id}")
    assert missing_res.status_code == 404
