"""
SQLite implementation of RagKeywordCollectionsRepository.

Uses a database file inside the rag_service module (e.g. data/rag_keywords.db).
No dependencies on other modules.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def _default_db_path() -> Path:
    """Return default DB path inside the rag_service package directory."""
    pkg_dir = Path(__file__).resolve().parent.parent
    data_dir = pkg_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "rag_keywords.db"


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rag_keyword_collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rag_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            FOREIGN KEY (collection_id) REFERENCES rag_keyword_collections(id) ON DELETE CASCADE,
            UNIQUE(collection_id, keyword)
        );
        CREATE INDEX IF NOT EXISTS ix_rag_keywords_collection_id ON rag_keywords(collection_id);
    """)


class KeywordCollectionsSqliteRepository:
    """SQLite-backed storage for RAG trigger keyword collections."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            _init_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, name, enabled, created_at, updated_at FROM rag_keyword_collections ORDER BY name"
            )
            rows = cur.fetchall()
            out = []
            for row in rows:
                cid = row["id"]
                cur_k = conn.execute(
                    "SELECT keyword FROM rag_keywords WHERE collection_id = ? ORDER BY keyword",
                    (cid,),
                )
                keywords = [r[0] for r in cur_k.fetchall()]
                out.append({
                    "id": cid,
                    "name": row["name"],
                    "enabled": bool(row["enabled"]),
                    "keywords": keywords,
                })
            return out

    def save_collection(
        self,
        collection_id: str | int | None,
        name: str,
        enabled: bool,
        keywords: list[str],
    ) -> str:
        with self._connect() as conn:
            now = _utc_now()
            if collection_id is None or collection_id == "":
                cid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO rag_keyword_collections (id, name, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (cid, name, 1 if enabled else 0, now, now),
                )
            else:
                cid = str(collection_id)
                conn.execute(
                    "UPDATE rag_keyword_collections SET name = ?, enabled = ?, updated_at = ? WHERE id = ?",
                    (name, 1 if enabled else 0, now, cid),
                )
                conn.execute("DELETE FROM rag_keywords WHERE collection_id = ?", (cid,))
            seen_lower: set[str] = set()
            for kw in keywords:
                k = (kw or "").strip()
                if not k:
                    continue
                kl = k.lower()
                if kl in seen_lower:
                    continue
                seen_lower.add(kl)
                conn.execute(
                    "INSERT INTO rag_keywords (collection_id, keyword) VALUES (?, ?)",
                    (cid, k),
                )
            conn.commit()
            return cid

    def delete_collection(self, collection_id: str | int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM rag_keyword_collections WHERE id = ?", (str(collection_id),))
            conn.commit()

    def get_enabled_keywords_flat(self) -> list[str]:
        with self._connect() as conn:
            cur = conn.execute("""
                SELECT k.keyword FROM rag_keywords k
                JOIN rag_keyword_collections c ON c.id = k.collection_id
                WHERE c.enabled = 1
            """)
            raw = [r[0] for r in cur.fetchall()]
        seen: set[str] = set()
        result: list[str] = []
        for w in raw:
            low = (w or "").lower()
            if low and low not in seen:
                seen.add(low)
                result.append(low)
        return result


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def get_keyword_collections_repository(db_path: str | Path | None = None) -> KeywordCollectionsSqliteRepository:
    """Factory: return a repository instance. DB path is resolved inside the module if not provided."""
    path = db_path
    if path is None and os.environ.get("RAG_KEYWORDS_DB_PATH"):
        path = os.environ["RAG_KEYWORDS_DB_PATH"]
    return KeywordCollectionsSqliteRepository(db_path=path)


__all__ = ["KeywordCollectionsSqliteRepository", "get_keyword_collections_repository"]
