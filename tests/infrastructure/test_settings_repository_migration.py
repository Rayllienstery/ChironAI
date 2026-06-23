"""SQLite schema migration smoke for SettingsRepository (Phase 5)."""

from __future__ import annotations

import sqlite3

import pytest

import infrastructure.database.session_manager as session_manager_module
from infrastructure.database.settings_repository import SettingsRepository


@pytest.mark.fast
@pytest.mark.infrastructure
def test_settings_repository_migrates_legacy_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    session_manager_module._session_manager = None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE model_tester_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                prompt_name TEXT,
                temperature REAL,
                top_p REAL,
                reasoning_level TEXT,
                use_rag INTEGER DEFAULT 1,
                rag_config TEXT
            )
            """
        )
        conn.commit()

    repo = SettingsRepository(db_path)
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(model_tester_settings)").fetchall()}
    assert {"model", "provider_id", "top_k"}.issubset(columns)

    repo.set_collection_meta(
        collection_name="ios-docs",
        framework_id="swiftui",
        version="1.0",
        last_refreshed_at="2026-01-01T00:00:00+00:00",
    )
    meta = repo.get_collection_meta("ios-docs")
    assert meta is not None
    assert meta["framework_id"] == "swiftui"
