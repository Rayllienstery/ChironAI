"""Database path resolution and row parsing for proxy journal logs."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

_PROXY_REQUEST_PREFIX = re.compile(r"^Proxy request\s*(?:\([^)]+\))?:\s*", re.IGNORECASE)


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """
    Resolve the WebUI SQLite database path.

    Priority:
    1) explicit ``db_path`` argument
    2) ``WEBUI_DB_PATH`` env var
    3) ``<project_root>/logs/webui.db``
    """
    if db_path is not None:
        return Path(db_path)
    env_path = os.getenv("WEBUI_DB_PATH")
    if env_path:
        return Path(env_path)
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "logs" / "webui.db"


def row_to_log_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite logs row to the canonical log dict shape."""
    log: dict[str, Any] = {
        "id": row["id"],
        "session_id": row["session_id"],
        "timestamp": row["timestamp"],
        "level": row["level"],
        "source": row["source"],
        "message": row["message"],
        "error_type": row["error_type"],
    }
    raw_metadata = row["metadata"]
    if raw_metadata:
        try:
            parsed = json.loads(raw_metadata)
            log["metadata"] = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            log["metadata"] = {}
    else:
        log["metadata"] = {}
    return log


def extract_user_message(log: dict[str, Any]) -> str:
    """Return user-facing text from a log row (metadata.user_query or message fallback)."""
    metadata = log.get("metadata")
    if isinstance(metadata, dict):
        user_query = metadata.get("user_query")
        if isinstance(user_query, str) and user_query.strip():
            return user_query
    message = log.get("message")
    if isinstance(message, str) and message.strip():
        return _PROXY_REQUEST_PREFIX.sub("", message).strip()
    return ""


def user_message_contains(user_message: str, substring: str) -> bool:
    """Case-insensitive Unicode substring match."""
    needle = (substring or "").casefold()
    if not needle:
        return False
    return needle in (user_message or "").casefold()
