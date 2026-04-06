"""
Persisted notification center entries for CoreUI (errors and history events).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from infrastructure.database.session_manager import get_session_manager


class NotificationsRepository:
    """SQLite persistence for CoreUI notification center rows."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.session_manager = get_session_manager(db_path)

    def add_notification(
        self,
        session_id: str,
        kind: str,
        source: str,
        title: str,
        message: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO coreui_notifications
                    (session_id, kind, source, title, message, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    kind,
                    source,
                    title,
                    message,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_notifications(
        self,
        session_id: str,
        limit: int = 200,
        include_dismissed: bool = True,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if include_dismissed:
                rows = conn.execute(
                    """
                    SELECT id, session_id, kind, source, title, message, metadata,
                           created_at, dismissed_at
                    FROM coreui_notifications
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, session_id, kind, source, title, message, metadata,
                           created_at, dismissed_at
                    FROM coreui_notifications
                    WHERE session_id = ? AND dismissed_at IS NULL
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def dismiss(self, session_id: str, notification_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE coreui_notifications
                SET dismissed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND session_id = ? AND dismissed_at IS NULL
                """,
                (notification_id, session_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def clear_session(self, session_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM coreui_notifications WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = {k: row[k] for k in row.keys()}
    meta = d.get("metadata")
    if isinstance(meta, str) and meta:
        try:
            d["metadata"] = json.loads(meta)
        except json.JSONDecodeError:
            d["metadata"] = None
    return d


_notifications_repository: Optional[NotificationsRepository] = None


def get_notifications_repository(db_path: Optional[str] = None) -> NotificationsRepository:
    global _notifications_repository
    if _notifications_repository is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _notifications_repository = NotificationsRepository(db_path)
    return _notifications_repository
