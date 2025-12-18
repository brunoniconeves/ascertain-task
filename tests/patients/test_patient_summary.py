from __future__ import annotations

from datetime import date, UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.llm.deps import get_openai_client
from app.core.llm.openai_client import OpenAIUpstreamError
from app.main import create_app
from tests.patients._helpers import create_patient


def _expected_age(*, dob: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)


class _FakeOpenAIClient:
    async def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        # Ensure we are returning structured JSON as required.
        return {"text": "Stub summary text."}


class _FailingOpenAIClient:
    async def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        raise OpenAIUpstreamError("upstream failed")


@pytest.fixture
def summary_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_openai_client] = lambda: _FakeOpenAIClient()
    with TestClient(app) as c:
        yield c


def test_get_patient_summary_success(summary_client: TestClient) -> None:
    patient_id = create_patient(client=summary_client, name="Ada Lovelace", date_of_birth="1990-12-10")
    taken_at = datetime.now(UTC).isoformat()
    resp = summary_client.post(
        f"/patients/{patient_id}/notes",
        json={"taken_at": taken_at, "note_type": "soap", "content_text": "S: test\nO: test"},
    )
    assert resp.status_code == 201, resp.text

    res = summary_client.get(f"/patients/{patient_id}/summary?audience=clinician&verbosity=medium")
    assert res.status_code == 200, res.text
    assert "X-Request-ID" in res.headers

    payload = res.json()
    assert payload["patient_heading"]["name"] == "Ada Lovelace"
    assert payload["patient_heading"]["mrn"].startswith("MRN-")
    assert payload["patient_heading"]["age"] == _expected_age(dob=date(1990, 12, 10))

    assert payload["summary"]["audience"] == "clinician"
    assert payload["summary"]["verbosity"] == "medium"
    assert payload["summary"]["text"] == "Stub summary text."


def test_get_patient_summary_invalid_audience_returns_400(summary_client: TestClient) -> None:
    patient_id = create_patient(client=summary_client, name="Test", date_of_birth="1990-01-01")
    res = summary_client.get(f"/patients/{patient_id}/summary?audience=bad&verbosity=medium")
    assert res.status_code == 400


def test_get_patient_summary_patient_not_found_returns_404(summary_client: TestClient) -> None:
    res = summary_client.get(
        "/patients/00000000-0000-0000-0000-000000000000/summary?audience=clinician&verbosity=medium"
    )
    assert res.status_code == 404


def test_get_patient_summary_llm_failure_returns_502() -> None:
    app = create_app()
    app.dependency_overrides[get_openai_client] = lambda: _FailingOpenAIClient()
    with TestClient(app) as client:
        patient_id = create_patient(client=client, name="Test", date_of_birth="1990-01-01")
        res = client.get(f"/patients/{patient_id}/summary?audience=clinician&verbosity=medium")
        assert res.status_code == 502
        assert res.json()["detail"] in {"LLM service failed", "LLM service unavailable"}


