"""
Repository for RAG test run history (persisted runs with results).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class RagTestRunsRepository:
    """Repository for storing and retrieving RAG test run history."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure rag_test_runs table exists (migration for existing DBs)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_test_runs (
                    id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    passed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    results TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_test_runs_created_at ON rag_test_runs(created_at)"
            )
            conn.commit()

    def add_run(
        self,
        run_id: str,
        model: str,
        status: str,
        total: int,
        passed: int,
        failed: int,
        results: list[dict[str, Any]],
        completed_at: str | None = None,
    ) -> None:
        """Persist a completed or cancelled run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO rag_test_runs (id, model, status, total, passed, failed, completed_at, results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    model,
                    status,
                    total,
                    passed,
                    failed,
                    completed_at or datetime.utcnow().isoformat(),
                    json.dumps(results),
                ),
            )
            conn.commit()

    def get_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        model: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent runs (newest first). Optional filters: model, from_date, to_date, status."""
        conditions: list[str] = []
        params: list[Any] = []
        if model and model.strip():
            conditions.append("model = ?")
            params.append(model.strip())
        if from_date and from_date.strip():
            conditions.append("created_at >= ?")
            params.append(from_date.strip())
        if to_date and to_date.strip():
            conditions.append("created_at <= ?")
            params.append(to_date.strip())
        if status and status.strip():
            conditions.append("status = ?")
            params.append(status.strip())
        where_sql = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"""
                SELECT id, model, status, total, passed, failed, created_at, completed_at
                FROM rag_test_runs
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "model": row["model"],
                "status": row["status"],
                "total": row["total"],
                "passed": row["passed"],
                "failed": row["failed"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
            }
            for row in rows
        ]

    def get_runs_summary(
        self,
        limit: int = 50,
        model: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Return aggregate metrics: total_runs, total_tests, total_passed, total_failed,
        pass_rate_pct, and per_model list of { model, run_count, total_passed, total_failed, pass_rate_pct }.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if model and model.strip():
            conditions.append("model = ?")
            params.append(model.strip())
        if from_date and from_date.strip():
            conditions.append("created_at >= ?")
            params.append(from_date.strip())
        if to_date and to_date.strip():
            conditions.append("created_at <= ?")
            params.append(to_date.strip())
        where_sql = " AND ".join(conditions) if conditions else "1=1"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Subquery to limit runs then aggregate
            cursor = conn.execute(
                f"""
                SELECT id, model, total, passed, failed
                FROM (
                    SELECT id, model, total, passed, failed, created_at
                    FROM rag_test_runs
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                params + [limit],
            )
            rows = cursor.fetchall()
        total_runs = len(rows)
        total_tests = sum(r["total"] for r in rows)
        total_passed = sum(r["passed"] for r in rows)
        total_failed = sum(r["failed"] for r in rows)
        pass_rate_pct = round((total_passed / total_tests * 100), 1) if total_tests else 0.0
        by_model: dict[str, dict[str, Any]] = {}
        for r in rows:
            m = r["model"] or "unknown"
            if m not in by_model:
                by_model[m] = {"model": m, "run_count": 0, "total_passed": 0, "total_failed": 0}
            by_model[m]["run_count"] += 1
            by_model[m]["total_passed"] += r["passed"]
            by_model[m]["total_failed"] += r["failed"]
        per_model = []
        for m, data in by_model.items():
            t = data["total_passed"] + data["total_failed"]
            per_model.append({
                "model": data["model"],
                "run_count": data["run_count"],
                "total_passed": data["total_passed"],
                "total_failed": data["total_failed"],
                "pass_rate_pct": round((data["total_passed"] / t * 100), 1) if t else 0.0,
            })
        per_model.sort(key=lambda x: -x["run_count"])
        return {
            "total_runs": total_runs,
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate_pct": pass_rate_pct,
            "per_model": per_model,
        }

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a single run with full results."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM rag_test_runs WHERE id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        results = []
        if row["results"]:
            try:
                results = json.loads(row["results"])
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": row["id"],
            "model": row["model"],
            "status": row["status"],
            "total": row["total"],
            "passed": row["passed"],
            "failed": row["failed"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "results": results,
        }


_rag_test_runs_repository: Optional[RagTestRunsRepository] = None


def get_rag_test_runs_repository(db_path: Optional[str] = None) -> RagTestRunsRepository:
    """Get or create global RagTestRunsRepository instance."""
    global _rag_test_runs_repository
    if _rag_test_runs_repository is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _rag_test_runs_repository = RagTestRunsRepository(db_path)
    return _rag_test_runs_repository
