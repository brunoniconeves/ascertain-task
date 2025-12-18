from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import BusinessValidationError

logger = logging.getLogger("app.business_validation")


def register_exception_handlers(app: FastAPI) -> None:
    """Register application exception handlers."""

    @app.exception_handler(BusinessValidationError)
    async def handle_business_validation_error(
        request: Request,
        exc: BusinessValidationError,
    ) -> JSONResponse:
        # IMPORTANT: do not log request bodies, query values, or any PHI.
        request_id = request.headers.get("X-Request-ID")
        logger.info(
            "Business validation failed",
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "request_path": request.url.path,  # no query string
                "status_code": 400,
                "error": "business_validation",
            },
        )
        return JSONResponse(status_code=400, content={"detail": exc.message})


