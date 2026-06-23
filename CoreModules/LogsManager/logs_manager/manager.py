"""Read-only proxy journal access for internal LLM consumers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from logs_manager.db import (
    extract_user_message,
    resolve_db_path,
    row_to_log_dict,
    user_message_contains,
)

_PROXY_JOURNAL_WHERE = (
    "session_id = 'proxy' AND source = 'proxy' AND level = 'INFO'"
)


class LogsManager:
    """Read persisted RAG Fusion proxy journal rows from ``logs/webui.db``."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = resolve_db_path(db_path)

    def get_latest_log(self) -> dict[str, Any] | None:
        """Return the newest proxy journal row, or ``None`` if the journal is empty."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT * FROM logs
                WHERE {_PROXY_JOURNAL_WHERE}
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return row_to_log_dict(row) if row is not None else None

    def get_log_by_id(self, log_id: int) -> dict[str, Any] | None:
        """Return a log row by primary key, or ``None`` if not found."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM logs WHERE id = ?",
                (int(log_id),),
            ).fetchone()
        return row_to_log_dict(row) if row is not None else None

    def find_latest_log_with_user_message(
        self,
        substring: str,
        *,
        scan_limit: int = 500,
    ) -> dict[str, Any] | None:
        """
        Return the newest proxy journal row whose user message contains ``substring``.

        User text is taken from ``metadata.user_query``, with ``message`` as fallback.
        Matching is case-insensitive for Unicode text (``casefold()``).
        """
        if not (substring or "").strip():
            return None

        limit = max(1, int(scan_limit))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM logs
                WHERE {_PROXY_JOURNAL_WHERE}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        for row in rows:
            log = row_to_log_dict(row)
            if user_message_contains(extract_user_message(log), substring):
                return log
        return None


_logs_manager: Optional[LogsManager] = None


def get_logs_manager(db_path: str | Path | None = None) -> LogsManager:
    """Get or create the global ``LogsManager`` instance."""
    global _logs_manager
    if _logs_manager is None or db_path is not None:
        _logs_manager = LogsManager(db_path)
    return _logs_manager
