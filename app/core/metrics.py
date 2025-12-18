from __future__ import annotations

import time
from typing import cast

from fastapi import APIRouter, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

metrics_router = APIRouter(tags=["monitoring"])

# IMPORTANT (healthcare safety):
# - Do not include identifiers (patient_id, MRN, etc.) in metric labels.
# - Route label MUST be a route template (e.g. /patients/{patient_id}) or a fixed value.

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "route", "status_code"),
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "route", "status_code"),
    # Buckets tuned for typical API latencies (fast endpoints + occasional slower work)
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def _safe_route_label(request: Request) -> str:
    """
    Return a safe route label.

    Prefer the Starlette/FastAPI route template (e.g. /patients/{patient_id}).
    If routing didn't match (404) or is otherwise unavailable, return "unmatched"
    to avoid leaking raw paths that may contain identifiers.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "unmatched"


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route_label = _safe_route_label(request)
            method = request.method
            code = str(int(status_code))
            duration = time.perf_counter() - started
            http_requests_total.labels(method=method, route=route_label, status_code=code).inc()
            http_request_duration_seconds.labels(
                method=method, route=route_label, status_code=code
            ).observe(duration)


@metrics_router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    # Use the default registry; sufficient for single-process dev usage.
    payload = generate_latest()
    return Response(content=cast(bytes, payload), media_type=CONTENT_TYPE_LATEST)
