"""Integration tests: list query validation."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_patient_list_filter_name_min_length_3(client: TestClient) -> None:
    res = client.get("/patients", params={"name": "ad"})
    assert res.status_code == 400
    assert "at least 3 characters" in res.json()["detail"]


