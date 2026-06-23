"""
Session management utilities for WebUI routes.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import g, request

from infrastructure.database import get_logs_repository, get_session_manager


def with_session(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to ensure a session exists for the request.
    Adds session_id to Flask g context.
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        session_id = request.args.get("session_id")
        if request.is_json:
            body = request.get_json(silent=True) or {}
            session_id = session_id or body.get("session_id")

        session_manager = get_session_manager()
        session = session_manager.get_or_create_session(session_id)

        # Store session_id in Flask g context
        g.session_id = session["id"]

        return f(*args, **kwargs)

    return decorated_function


def log_to_database(level: str, message: str, source: str | None = None, error_type: str | None = None) -> None:
    """Helper to log to database if session_id is available in Flask g context."""
    try:
        session_id = getattr(g, "session_id", None)
        if not session_id:
            return

        logs_repo = get_logs_repository()
        logs_repo.add_log(
            session_id=session_id,
            level=level,
            message=message,
            source=source,
            error_type=error_type,
        )
    except Exception:
        # Don't fail if logging fails
        pass
