"""Centralized logging configuration.

This config is intentionally designed for healthcare environments:
- Structured logs (JSON) to stdout for centralized collection (Docker/K8s/etc.)
- No request/response bodies, no query strings, no headers are logged by default
- Extra fields are optional; the formatter must never raise due to missing keys
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from typing import Any


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class JsonFormatter(logging.Formatter):
    """Emit JSON logs while safely handling missing `extra` fields.

    We avoid the classic `'%(request_id)s'`-style formatter because it raises KeyError
    when a record doesn't include those fields (e.g. third-party logs).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            # Correlation / request metadata (may not exist on all records)
            "request_id": getattr(record, "request_id", None),
            "method": getattr(record, "method", getattr(record, "http_method", None)),
            "path": getattr(record, "path", getattr(record, "request_path", None)),
            "status_code": getattr(record, "status_code", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Configure application logging (JSON to stdout)."""

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "app.core.logging.JsonFormatter",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "level": LOG_LEVEL,
                "handlers": ["default"],
            },
        }
    )


