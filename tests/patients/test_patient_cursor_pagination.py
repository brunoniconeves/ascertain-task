"""Integration tests: patient cursor pagination + ordering contracts."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.patients._helpers import create_patient


def test_patient_cursor_pagination_ordered_by_name(client: TestClient) -> None:
    """Cursor pagination preserves ordering and avoids duplicates."""
    create_patient(client=client, name="Ada Lovelace", date_of_birth="1815-12-10")
    create_patient(client=client, name="Alan Turing", date_of_birth="1912-06-23")
    create_patient(client=client, name="Grace Hopper", date_of_birth="1906-12-09")

    page1 = client.get("/patients", params={"limit": 2, "sort": "name", "order": "asc"})
    assert page1.status_code == 200
    p1 = page1.json()

    page1_items = p1["items"]
    assert page1_items == sorted(page1_items, key=lambda p: p["name"])
    assert p1["next_cursor"] is not None

    page2 = client.get(
        "/patients",
        params={"limit": 2, "sort": "name", "order": "asc", "cursor": p1["next_cursor"]},
    )
    assert page2.status_code == 200
    p2 = page2.json()
    page2_items = p2["items"]
    assert page2_items == sorted(page2_items, key=lambda p: p["name"])

    assert set(p["id"] for p in page1_items).isdisjoint({p["id"] for p in page2_items})
