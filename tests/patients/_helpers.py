"""Test helpers for the patients slice."""

from __future__ import annotations

from starlette.testclient import TestClient


def create_patient(*, client: TestClient, name: str, date_of_birth: str) -> str:
    """Create a patient and return its id."""
    # Safety: never follow redirects on POST. A 307/308 would re-POST and can create duplicates.
    res = client.post(
        "/patients",
        json={"name": name, "date_of_birth": date_of_birth},
        follow_redirects=False,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]
