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
    """SQLite persistence for CoreUI notification-center rows.

    Args:
        db_path: Path to the SQLite database. Parent directory is created if missing.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.session_manager = get_session_manager(db_path)
        self._ensure_notification_columns()

    def _ensure_notification_columns(self) -> None:
        """Ensure notification table has additive columns required by newer UI features."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                cols = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(coreui_notifications)").fetchall()
                }
                if not cols:
                    return
                if "is_console_error" not in cols:
                    conn.execute(
                        "ALTER TABLE coreui_notifications ADD COLUMN is_console_error INTEGER NOT NULL DEFAULT 0"
                    )
                if "aggregation_key" not in cols:
                    conn.execute(
                        "ALTER TABLE coreui_notifications ADD COLUMN aggregation_key TEXT"
                    )
                if "occurrence_count" not in cols:
                    conn.execute(
                        "ALTER TABLE coreui_notifications ADD COLUMN occurrence_count INTEGER NOT NULL DEFAULT 1"
                    )
                if "last_occurrence_at" not in cols:
                    # SQLite ALTER TABLE is stricter than CREATE TABLE: avoid non-constant defaults here.
                    conn.execute(
                        "ALTER TABLE coreui_notifications ADD COLUMN last_occurrence_at TIMESTAMP"
                    )
                conn.execute(
                    """
                    UPDATE coreui_notifications
                    SET last_occurrence_at = COALESCE(last_occurrence_at, created_at, CURRENT_TIMESTAMP)
                    WHERE last_occurrence_at IS NULL
                    """
                )
                conn.execute(
                    """
                    UPDATE coreui_notifications
                    SET occurrence_count = COALESCE(occurrence_count, 1)
                    WHERE occurrence_count IS NULL
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_coreui_notifications_aggregate
                    ON coreui_notifications(session_id, aggregation_key, dismissed_at)
                    """
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass

    def add_notification(
        self,
        session_id: str,
        kind: str,
        source: str,
        title: str,
        message: str = "",
        metadata: Optional[dict[str, Any]] = None,
        aggregation_key: Optional[str] = None,
        is_console_error: bool = False,
    ) -> int:
        for attempt in range(2):
            try:
                with sqlite3.connect(self.db_path) as conn:
                    if aggregation_key:
                        existing = conn.execute(
                            """
                            SELECT id
                            FROM coreui_notifications
                            WHERE session_id = ?
                              AND aggregation_key = ?
                              AND dismissed_at IS NULL
                            ORDER BY id DESC
                            LIMIT 1
                            """,
                            (session_id, aggregation_key),
                        ).fetchone()
                        if existing is not None:
                            conn.execute(
                                """
                                UPDATE coreui_notifications
                                SET kind = ?,
                                    source = ?,
                                    title = ?,
                                    message = ?,
                                    metadata = ?,
                                    is_console_error = ?,
                                    occurrence_count = COALESCE(occurrence_count, 1) + 1,
                                    last_occurrence_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                                """,
                                (
                                    kind,
                                    source,
                                    title,
                                    message,
                                    json.dumps(metadata) if metadata else None,
                                    1 if is_console_error else 0,
                                    int(existing[0]),
                                ),
                            )
                            conn.commit()
                            return int(existing[0])
                    cursor = conn.execute(
                        """
                        INSERT INTO coreui_notifications
                            (
                                session_id, kind, source, title, message, metadata,
                                aggregation_key, occurrence_count, last_occurrence_at, is_console_error
                            )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
                        """,
                        (
                            session_id,
                            kind,
                            source,
                            title,
                            message,
                            json.dumps(metadata) if metadata else None,
                            aggregation_key,
                            1 if is_console_error else 0,
                        ),
                    )
                    conn.commit()
                    return int(cursor.lastrowid)
            except sqlite3.OperationalError:
                if attempt == 0:
                    self._ensure_notification_columns()
                    continue
                raise
        raise RuntimeError("add_notification retry loop exhausted")

    def list_notifications(
        self,
        session_id: str,
        limit: int = 200,
        include_dismissed: bool = True,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                if include_dismissed:
                    rows = conn.execute(
                        """
                        SELECT id, session_id, kind, source, title, message, metadata, aggregation_key,
                               occurrence_count, is_console_error, created_at, last_occurrence_at, dismissed_at
                        FROM coreui_notifications
                        WHERE session_id = ?
                        ORDER BY COALESCE(last_occurrence_at, created_at) DESC, id DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, session_id, kind, source, title, message, metadata, aggregation_key,
                               occurrence_count, is_console_error, created_at, last_occurrence_at, dismissed_at
                        FROM coreui_notifications
                        WHERE session_id = ? AND dismissed_at IS NULL
                        ORDER BY COALESCE(last_occurrence_at, created_at) DESC, id DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
            except sqlite3.OperationalError:
                if include_dismissed:
                    rows = conn.execute(
                        """
                        SELECT id, session_id, kind, source, title, message, metadata,
                               NULL AS aggregation_key, 1 AS occurrence_count,
                               is_console_error, created_at, created_at AS last_occurrence_at, dismissed_at
                        FROM coreui_notifications
                        WHERE session_id = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, session_id, kind, source, title, message, metadata,
                               NULL AS aggregation_key, 1 AS occurrence_count,
                               is_console_error, created_at, created_at AS last_occurrence_at, dismissed_at
                        FROM coreui_notifications
                        WHERE session_id = ? AND dismissed_at IS NULL
                        ORDER BY created_at DESC, id DESC
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
    d = {k: row[k] for k in row.keys()}  # noqa: SIM118 - sqlite3.Row iterates values, not column names.
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
