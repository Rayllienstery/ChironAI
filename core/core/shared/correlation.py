"""Correlation id helpers for long-running jobs and structured logging."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_HEADER_NAMES = (
    "X-Correlation-Id",
    "X-Request-Id",
    "X-Trace-Id",
    "Trace-Id",
    "Request-Id",
)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def resolve_correlation_id(existing: str | None = None) -> str:
    """Resolve correlation id from explicit value, inbound HTTP headers, or a new uuid."""
    if existing and str(existing).strip():
        return str(existing).strip()
    try:
        from flask import has_request_context, request

        if has_request_context():
            for name in _HEADER_NAMES:
                value = request.headers.get(name)
                if value and str(value).strip():
                    return str(value).strip()
    except ImportError:
        pass
    return new_correlation_id()


def log_operation(
    logger: logging.Logger,
    level: int,
    *,
    operation: str,
    correlation_id: str,
    message: str,
    **extra: Any,
) -> None:
    logger.log(
        level,
        "%s [correlation_id=%s operation=%s]",
        message,
        correlation_id,
        operation,
        extra={"correlation_id": correlation_id, "operation": operation, **extra},
    )


def safe_optional(
    logger: logging.Logger,
    *,
    operation: str,
    correlation_id: str,
    fn: Callable[[], T],
    default: T | None = None,
    reason: str = "",
) -> T | None:
    """Run optional work; log and return default instead of raising."""
    try:
        return fn()
    except Exception as exc:  # safe: optional dependency / cleanup path
        log_operation(
            logger,
            logging.WARNING,
            operation=operation,
            correlation_id=correlation_id,
            message=reason or f"optional step skipped: {exc}",
            error=str(exc),
        )
        return default
