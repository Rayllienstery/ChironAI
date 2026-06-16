"""
Logs repository for storing and retrieving WebUI logs.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from infrastructure.database.session_manager import get_session_manager


def _normalize_log_timestamp_bound(value: str, *, end: bool) -> str:
    """
    Convert ISO-8601 (e.g. from JS toISOString) to SQLite TIMESTAMP lexicographic form.

    SQLite stores CURRENT_TIMESTAMP as 'YYYY-MM-DD HH:MM:SS'. Comparing that to
    strings containing 'T' or 'Z' breaks lexicographic lower bounds.
    """
    s = (value or "").strip()
    if not s:
        return s
    dt: Optional[datetime] = None
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        elif "T" in s:
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            if end:
                dt = dt.replace(hour=23, minute=59, second=59)
            else:
                dt = dt.replace(hour=0, minute=0, second=0)
    except ValueError:
        return s
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class LogsRepository:
    """Repository for storing and retrieving logs from SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.session_manager = get_session_manager(db_path)

    def add_log(
        self,
        session_id: str,
        level: str,
        message: str,
        source: Optional[str] = None,
        error_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Add a log entry.
        
        Returns:
            Log ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs (session_id, level, source, message, error_type, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    level,
                    source,
                    message,
                    error_type,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_logs(
        self,
        session_id: str,
        level: Optional[str] = None,
        limit: int = 100,
        since_id: Optional[int] = None,
        source: Optional[str] = None,
        include_system: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        autocomplete_only: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        Get logs for a session.

        Args:
            session_id: Session ID
            level: Filter by level (ERROR, WARNING, INFO, etc.)
            limit: Maximum number of logs to return
            since_id: Only return logs with ID > since_id (for incremental updates)
            source: Filter by source
            include_system: Include system session logs
            from_date: Only return logs with timestamp >= from_date (ISO or YYYY-MM-DD)
            to_date: Only return logs with timestamp <= to_date (ISO or YYYY-MM-DD)
            autocomplete_only: If True, only rows whose metadata JSON has is_autocomplete true

        Returns:
            List of log dicts
        """
        if from_date is not None:
            from_date = _normalize_log_timestamp_bound(from_date, end=False)
        if to_date is not None:
            to_date = _normalize_log_timestamp_bound(to_date, end=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Always include logs for the current session and, optionally,
            # system-wide logs (session_id='system') so global errors are visible.
            if include_system:
                query = "SELECT * FROM logs WHERE (session_id = ? OR session_id = 'system')"
                params: list[Any] = [session_id]
            else:
                query = "SELECT * FROM logs WHERE session_id = ?"
                params = [session_id]

            if since_id is not None:
                query += " AND id > ?"
                params.append(since_id)

            if level:
                query += " AND level = ?"
                params.append(level)

            if source:
                query += " AND source = ?"
                params.append(source)

            if from_date is not None:
                query += " AND timestamp >= ?"
                params.append(from_date)

            if to_date is not None:
                query += " AND timestamp <= ?"
                params.append(to_date)

            if autocomplete_only is True:
                query += (
                    " AND metadata IS NOT NULL "
                    "AND json_extract(metadata, '$.is_autocomplete') = 1"
                )

            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log: dict[str, Any] = {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "level": row["level"],
                    "source": row["source"],
                    "message": row["message"],
                    "error_type": row["error_type"],
                }
                if row["metadata"]:
                    try:
                        log["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        log["metadata"] = {}
                logs.append(log)
            
            # Return in chronological order (oldest first)
            logs.reverse()
            return logs

    def get_all_logs(
        self,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get all logs (across all sessions)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM logs"
            params: list[Any] = []
            
            if level:
                query += " WHERE level = ?"
                params.append(level)
            
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log: dict[str, Any] = {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "level": row["level"],
                    "source": row["source"],
                    "message": row["message"],
                    "error_type": row["error_type"],
                }
                if row["metadata"]:
                    try:
                        log["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        log["metadata"] = {}
                logs.append(log)
            
            logs.reverse()
            return logs

    def delete_logs_for_session(
        self,
        session_id: str,
        *,
        include_system: bool = True,
    ) -> int:
        """Delete log rows for a WebUI session; optionally shared ``system`` rows (same as GET)."""
        with sqlite3.connect(self.db_path) as conn:
            if include_system:
                cursor = conn.execute(
                    "DELETE FROM logs WHERE session_id = ? OR session_id = 'system'",
                    (session_id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM logs WHERE session_id = ?",
                    (session_id,),
                )
            conn.commit()
            return cursor.rowcount or 0

    def delete_proxy_logs(self, *, autocomplete_only: bool = False) -> int:
        """Delete proxy request logs (``session_id='proxy'``, ``source='proxy'``)."""
        with sqlite3.connect(self.db_path) as conn:
            query = "DELETE FROM logs WHERE session_id = 'proxy' AND source = 'proxy'"
            if autocomplete_only:
                query += (
                    " AND metadata IS NOT NULL "
                    "AND json_extract(metadata, '$.is_autocomplete') = 1"
                )
            cursor = conn.execute(query)
            conn.commit()
            return cursor.rowcount or 0


# Global instance
_logs_repository: Optional[LogsRepository] = None


def get_logs_repository(db_path: Optional[str] = None) -> LogsRepository:
    """Get or create global LogsRepository instance."""
    global _logs_repository
    if _logs_repository is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _logs_repository = LogsRepository(db_path)
    return _logs_repository

