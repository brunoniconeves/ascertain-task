"""Integration tests: patient list filtering."""

from __future__ import annotations

# ruff: noqa: I001
from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_patient_list_filter_by_name_case_insensitive(client: TestClient) -> None:
    """Filtering is case-insensitive and matches substrings."""
    ada_id = create_patient(client=client, name="Ada Lovelace", date_of_birth="1815-12-10")
    _alan_id = create_patient(client=client, name="Alan Turing", date_of_birth="1912-06-23")

    res = client.get("/patients", params={"name": "ada", "limit": 50})
    assert res.status_code == 200
    payload = res.json()

    assert "items" in payload
    assert "next_cursor" in payload
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == ada_id
