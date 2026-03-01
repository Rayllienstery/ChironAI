"""
Settings repository for storing WebUI and Model Tester settings.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from infrastructure.database.session_manager import get_session_manager


class SettingsRepository:
    """Repository for storing and retrieving settings from SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.session_manager = get_session_manager(db_path)
        self._migrate_schema()

    def get_tester_settings(self, session_id: str) -> Optional[dict[str, Any]]:
        """Get Model Tester settings for a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM model_tester_settings WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            # sqlite3.Row has no .get(); convert to dict for safe .get() and optional keys
            row = {k: row[k] for k in row.keys()}

            settings: dict[str, Any] = {
                "id": row["id"],
                "session_id": row["session_id"],
                "prompt_name": row.get("prompt_name"),
                "swift_mode": row.get("swift_mode"),
                "temperature": row.get("temperature"),
                "top_p": row.get("top_p"),
                "reasoning_level": row.get("reasoning_level"),
                "use_rag": bool(row.get("use_rag", 1)),
            }
            
            # Handle optional fields that may not exist in older schemas
            if "model" in row:
                settings["model"] = row.get("model")
            if "top_k" in row:
                settings["top_k"] = row.get("top_k")
            
            if row.get("rag_config"):
                try:
                    settings["rag_config"] = json.loads(row["rag_config"])
                except json.JSONDecodeError:
                    settings["rag_config"] = {}
            
            return settings

    def save_tester_settings(self, session_id: str, settings: dict[str, Any]) -> int:
        """Save Model Tester settings for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO model_tester_settings 
                (session_id, model, prompt_name, swift_mode, temperature, top_p, reasoning_level, use_rag, top_k, rag_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    settings.get("model"),
                    settings.get("prompt_name"),
                    settings.get("swift_mode"),
                    settings.get("temperature"),
                    settings.get("top_p"),
                    settings.get("reasoning_level"),
                    1 if settings.get("use_rag", True) else 0,
                    settings.get("top_k"),
                    json.dumps(settings.get("rag_config", {})) if settings.get("rag_config") else None,
                ),
            )
            conn.commit()
            return cursor.lastrowid
    
    def _migrate_schema(self) -> None:
        """Migrate database schema to add new columns if needed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if 'model' column exists
            cursor.execute("PRAGMA table_info(model_tester_settings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "model" not in columns:
                try:
                    conn.execute("ALTER TABLE model_tester_settings ADD COLUMN model TEXT")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column might already exist
            
            if "top_k" not in columns:
                try:
                    conn.execute("ALTER TABLE model_tester_settings ADD COLUMN top_k INTEGER")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column might already exist

    def get_app_setting(self, key: str) -> Optional[str]:
        """Get an app setting value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_app_setting(self, key: str, value: str) -> None:
        """Set an app setting value."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
            conn.commit()

    def get_all_app_settings(self) -> dict[str, str]:
        """Get all app settings."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT key, value FROM app_settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}


# Global instance
_settings_repository: Optional[SettingsRepository] = None


def get_settings_repository(db_path: Optional[str] = None) -> SettingsRepository:
    """Get or create global SettingsRepository instance."""
    global _settings_repository
    if _settings_repository is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _settings_repository = SettingsRepository(db_path)
    return _settings_repository

