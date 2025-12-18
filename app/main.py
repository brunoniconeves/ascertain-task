from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html
from starlette.staticfiles import StaticFiles

from app.api.exception_handlers import register_exception_handlers
from app.api.schemas import HealthOut
from app.core.db import close_db, init_db
from app.core.logging import setup_logging
from app.core.metrics import PrometheusMetricsMiddleware, metrics_router
from app.core.middleware.http_logging import HttpLoggingMiddleware
from app.core.settings import get_settings
from app.patients.router import router as patients_router

setup_logging()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Defer settings/env access until application startup.
        # This avoids requiring DATABASE_URL at import time (e.g. during pytest collection in CI).
        settings = get_settings()
        init_db(app=app, database_url=str(settings.database_url))
        yield
        await close_db(app=app)

    app = FastAPI(
        title="Healthcare Data Processing API",
        description=(
            "API for managing patients and their clinical notes.\n\n"
            "Design principles:\n"
            "- Patient notes are stored as the *source of truth* (raw text or uploaded files).\n"
            "- Any structured data (e.g. derived SOAP sections) is best-effort and "
            "non-authoritative.\n"
            "- Logging and metrics avoid PHI/PII by using route templates and metadata only."
        ),
        lifespan=lifespan,
        docs_url="/swagger",  # Swagger UI ("Try it out")
        redoc_url=None,  # we'll serve a custom ReDoc page at /docs
        openapi_tags=[
            {
                "name": "health",
                "description": (
                    "Basic uptime and readiness checks for load balancers and monitoring."
                ),
            },
            {
                "name": "patients",
                "description": "Create, read, update and delete patient records.",
            },
            {
                "name": "patient-notes",
                "description": (
                    "Manage patient notes (inline text or file uploads). Notes may include "
                    "optional derived structured data (e.g. SOAP sections) when available."
                ),
            },
            {
                "name": "metrics",
                "description": "Prometheus-compatible metrics endpoint.",
            },
        ],
    )

    app.add_middleware(PrometheusMetricsMiddleware)
    app.add_middleware(HttpLoggingMiddleware)

    register_exception_handlers(app)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/docs", include_in_schema=False)
    async def redoc_docs():
        local_redoc = static_dir / "redoc.standalone.js"
        redoc_js_url = (
            "/static/redoc.standalone.js"
            if local_redoc.exists()
            else ("https://cdn.jsdelivr.net/npm/redoc@2.1.4/bundles/redoc.standalone.js")
        )
        return get_redoc_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{app.title} - ReDoc",
            redoc_js_url=redoc_js_url,
        )

    @app.get(
        "/health",
        response_model=HealthOut,
        tags=["health"],
        summary="Health check",
        description=(
            "Lightweight endpoint to verify the API process is running.\n\n"
            "This endpoint intentionally does not check downstream dependencies (e.g. DB) so it "
            "can be used safely for basic uptime checks."
        ),
    )
    async def health() -> HealthOut:
        return HealthOut(status="ok")

    app.include_router(metrics_router)
    app.include_router(patients_router)
    return app


app = create_app()
