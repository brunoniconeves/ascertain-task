"""HTTP logging middleware for healthcare environments.

Design goals:
- Log *metadata only* (no request/response bodies, no query strings, no sensitive headers).
- Generate or propagate X-Request-ID for correlation.
- Structured logging using the standard library logger `extra` fields.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger("app.http")

_REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _get_or_create_request_id(*, request: Request) -> str:
    """Return a safe request id, either propagated or newly generated.

    We only accept a narrow character set and length to avoid log injection and
    other unexpected values. If invalid, we generate a new UUID4.
    """

    candidate = request.headers.get(_REQUEST_ID_HEADER)
    if candidate and _SAFE_REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _safe_route_label(*, request: Request) -> str:
    """
    Return a safe path label for logs.

    Prefer the framework's route template (e.g. /patients/{patient_id}) to avoid
    logging identifiers present in raw URLs.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "unmatched"


class HttpLoggingMiddleware(BaseHTTPMiddleware):
    """Log request/response metadata and propagate a correlation id.

    IMPORTANT: This middleware intentionally does NOT log:
    - request body / response body (may contain PHI)
    - query string values (may contain PHI, e.g. patient names)
    - headers (may contain auth tokens or PHI)
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _get_or_create_request_id(request=request)
        started = time.perf_counter()
        # Make request_id available to downstream handlers/services for safe correlation logging.
        # This avoids re-generating IDs or reading query/body data for correlation.
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - we must log unexpected exceptions with stack trace
            duration_ms = (time.perf_counter() - started) * 1000.0
            safe_path = _safe_route_label(request=request)
            logger.exception(
                "Unhandled exception while processing request",
                extra={
                    "request_id": request_id,
                    "http_method": request.method,
                    "request_path": safe_path,
                    "status_code": 500,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000.0
        safe_path = _safe_route_label(request=request)

        # Ensure correlation id is present on all responses.
        response.headers[_REQUEST_ID_HEADER] = request_id

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "request_path": safe_path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
