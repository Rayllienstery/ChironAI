"""
Logs repository for storing and retrieving WebUI logs.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from infrastructure.database.session_manager import get_session_manager


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
    ) -> list[dict[str, Any]]:
        """
        Get logs for a session.
        
        Args:
            session_id: Session ID
            level: Filter by level (ERROR, WARNING, INFO, etc.)
            limit: Maximum number of logs to return
            since_id: Only return logs with ID > since_id (for incremental updates)
        
        Returns:
            List of log dicts
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM logs WHERE session_id = ?"
            params: list[Any] = [session_id]
            
            if since_id is not None:
                query += " AND id > ?"
                params.append(since_id)
            
            if level:
                query += " AND level = ?"
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

