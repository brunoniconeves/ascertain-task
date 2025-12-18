"""Integration tests: patient business validation."""

from __future__ import annotations

from datetime import date

from starlette.testclient import TestClient


def test_create_patient_rejects_future_date_of_birth(client: TestClient) -> None:
    # Use a far-future date to avoid flakiness around time zones / midnight boundaries.
    res = client.post("/patients", json={"name": "Future Person", "date_of_birth": "2999-01-01"})
    assert res.status_code == 400
    assert "date_of_birth" in res.json()["detail"]


