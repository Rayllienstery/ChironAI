"""Structured JSON logging helpers with request correlation fields."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

_DEFAULT_REQUEST_ID = "-"
_DEFAULT_TRACE_ID = "-"


def _record_value(record: logging.LogRecord, name: str, default: str = "") -> str:
    value = getattr(record, name, default)
    return str(value if value is not None else default)


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as JSON with stable observability fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": _record_value(record, "component", record.module),
            "request_id": _record_value(record, "request_id", _DEFAULT_REQUEST_ID),
            "trace_id": _record_value(record, "trace_id", _DEFAULT_TRACE_ID),
            "message": record.getMessage(),
        }
        operation = getattr(record, "operation", None)
        if operation:
            payload["operation"] = str(operation)
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            payload["correlation_id"] = str(correlation_id)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_structured_logger(logger: logging.Logger) -> logging.Logger:
    """Attach JSON formatting to existing handlers without replacing them."""

    if not logger.handlers:
        handler = logging.StreamHandler()
        logger.addHandler(handler)
    for handler in logger.handlers:
        handler.setFormatter(StructuredJsonFormatter())
    logger.propagate = False
    return logger


__all__ = ["StructuredJsonFormatter", "configure_structured_logger"]
