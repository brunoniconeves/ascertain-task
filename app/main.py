from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html
from starlette.staticfiles import StaticFiles

from app.api.exception_handlers import register_exception_handlers
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
        lifespan=lifespan,
        docs_url="/swagger",  # Swagger UI ("Try it out")
        redoc_url=None,  # we'll serve a custom ReDoc page at /docs
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(metrics_router)
    app.include_router(patients_router)
    return app


app = create_app()
