"""
Session management for WebUI.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SessionManager:
    """Manages WebUI sessions in SQLite database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            schema = _SCHEMA_PATH.read_text(encoding="utf-8")
            conn.executescript(schema)
            self._migrate_schema(conn)
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """
        Apply lightweight migrations for existing DBs.

        We intentionally keep this minimal and additive only (ALTER TABLE ADD COLUMN),
        since SQLite doesn't support many schema changes without table rebuilds.
        """
        try:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(coreui_notifications)").fetchall()
            }
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
                conn.execute(
                    "ALTER TABLE coreui_notifications ADD COLUMN last_occurrence_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
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
                CREATE INDEX IF NOT EXISTS idx_coreui_notifications_aggregate
                ON coreui_notifications(session_id, aggregation_key, dismissed_at)
                """
            )
        except sqlite3.OperationalError:
            # Table might not exist yet (fresh DB) or PRAGMA failed; schema.sql covers creation.
            pass

    def get_or_create_session(self, session_id: Optional[str] = None) -> dict[str, str]:
        """
        Get existing session or create new one.
        
        Returns:
            dict with 'id', 'created_at', 'last_activity'
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if session_id:
                cursor = conn.execute(
                    "SELECT id, created_at, last_activity FROM sessions WHERE id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row:
                    # Update last activity
                    conn.execute(
                        "UPDATE sessions SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                        (session_id,),
                    )
                    conn.commit()
                    return {
                        "id": row["id"],
                        "created_at": row["created_at"],
                        "last_activity": row["last_activity"],
                    }
            
            # Create new session
            new_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO sessions (id, created_at, last_activity) VALUES (?, ?, ?)",
                (new_id, now, now),
            )
            conn.commit()
            return {
                "id": new_id,
                "created_at": now,
                "last_activity": now,
            }

    def update_activity(self, session_id: str) -> None:
        """Update last activity timestamp for session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,),
            )
            conn.commit()


# Global instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(db_path: Optional[str] = None) -> SessionManager:
    """Get or create global SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _session_manager = SessionManager(db_path)
    return _session_manager
