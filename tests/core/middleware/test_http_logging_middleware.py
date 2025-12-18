"""Unit tests for the HTTP logging middleware.

We assert structured log fields via `caplog` (not message strings) and verify:
- X-Request-ID is generated or propagated
- Successful requests emit exactly one INFO log entry with metadata only
- Unhandled exceptions emit an ERROR log entry with a stack trace and return 500
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware.http_logging import HttpLoggingMiddleware


def _make_app() -> FastAPI:
    """Create a minimal app for middleware unit tests."""
    app = FastAPI()
    app.add_middleware(HttpLoggingMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return app


def _get_http_log_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.http"]


def test_successful_request_sets_request_id_and_logs_one_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A successful request should emit one INFO log with required metadata and include X-Request-ID."""
    caplog.set_level(logging.INFO, logger="app.http")
    app = _make_app()

    with TestClient(app) as client:
        res = client.get("/health?patient_name=Jane+Doe")

    assert res.status_code == 200
    assert "x-request-id" in res.headers
    assert res.headers["x-request-id"]

    records = _get_http_log_records(caplog)
    info_records = [r for r in records if r.levelno == logging.INFO]
    assert len(info_records) == 1

    record = info_records[0]
    # The LogRecord's 'extra' fields are in record.__dict__, so access these as needed
    assert record.__dict__["request_id"] == res.headers["x-request-id"]
    assert record.__dict__["http_method"] == "GET"
    # Must not include query string values (may contain PHI).
    assert record.__dict__["request_path"] == "/health"
    assert record.__dict__["status_code"] == 200

    duration_ms = record.__dict__["duration_ms"]
    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0


def test_propagates_valid_request_id(caplog: pytest.LogCaptureFixture) -> None:
    """If a valid X-Request-ID is provided, the middleware should propagate it."""
    caplog.set_level(logging.INFO, logger="app.http")
    app = _make_app()

    with TestClient(app) as client:
        res = client.get("/health", headers={"X-Request-ID": "req_abc-123"})

    assert res.status_code == 200
    assert res.headers["x-request-id"] == "req_abc-123"

    records = _get_http_log_records(caplog)
    info_records = [r for r in records if r.levelno == logging.INFO]
    assert len(info_records) == 1
    assert info_records[0].__dict__["request_id"] == "req_abc-123"


def test_unhandled_exception_returns_500_and_logs_error_with_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled exceptions should return 500 and emit one ERROR log record with exc_info."""
    caplog.set_level(logging.INFO, logger="app.http")
    app = _make_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/boom", headers={"X-Request-ID": "req_err_001"})

    assert res.status_code == 500

    records = _get_http_log_records(caplog)
    error_records = [r for r in records if r.levelno == logging.ERROR]
    assert len(error_records) == 1

    record = error_records[0]
    assert record.__dict__["request_id"] == "req_err_001"
    assert record.__dict__["http_method"] == "GET"
    assert record.__dict__["request_path"] == "/boom"
    assert record.__dict__["status_code"] == 500

    duration_ms = record.__dict__["duration_ms"]
    assert isinstance(duration_ms, (int, float))
    assert duration_ms >= 0

    # Stack trace is required for unhandled exceptions.
    assert record.exc_info
