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

from application.rag_tests.metrics import normalize_rag_test_result, normalize_rag_test_run


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
                    provider_id TEXT,
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
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(rag_test_runs)").fetchall()
            }
            if "provider_id" not in columns:
                conn.execute("ALTER TABLE rag_test_runs ADD COLUMN provider_id TEXT")
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
        provider_id: str | None = None,
    ) -> None:
        """Persist a completed or cancelled run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO rag_test_runs (id, provider_id, model, status, total, passed, failed, completed_at, results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    (provider_id or "").strip() or None,
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
        provider_id: str | None = None,
        model: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent runs (newest first). Optional filters: model, from_date, to_date, status."""
        conditions: list[str] = []
        params: list[Any] = []
        if provider_id and provider_id.strip():
            conditions.append("provider_id = ?")
            params.append(provider_id.strip())
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
                SELECT id, provider_id, model, status, total, passed, failed, created_at, completed_at
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
                "provider_id": row["provider_id"],
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
        provider_id: str | None = None,
        model: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Return aggregate metrics:
        - total_runs, total_tests, total_passed, total_failed, pass_rate_pct
        - per_model: list of { model, run_count, total_passed, total_failed, pass_rate_pct }
        - domains: aggregate by logical domain (UIKit / SwiftUI / Swift) and difficulty.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if provider_id and provider_id.strip():
            conditions.append("provider_id = ?")
            params.append(provider_id.strip())
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
                SELECT id, provider_id, model, total, passed, failed
                FROM (
                    SELECT id, provider_id, model, total, passed, failed, created_at
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
            provider = str(r["provider_id"] or "").strip()
            model_name = r["model"] or "unknown"
            key = f"{provider}:{model_name}" if provider else str(model_name)
            if key not in by_model:
                by_model[key] = {
                    "provider_id": provider or None,
                    "model": model_name,
                    "run_count": 0,
                    "total_passed": 0,
                    "total_failed": 0,
                }
            by_model[key]["run_count"] += 1
            by_model[key]["total_passed"] += r["passed"]
            by_model[key]["total_failed"] += r["failed"]
        per_model = []
        for _key, data in by_model.items():
            t = data["total_passed"] + data["total_failed"]
            per_model.append({
                "provider_id": data["provider_id"],
                "model": data["model"],
                "run_count": data["run_count"],
                "total_passed": data["total_passed"],
                "total_failed": data["total_failed"],
                "pass_rate_pct": round((data["total_passed"] / t * 100), 1) if t else 0.0,
            })
        per_model.sort(key=lambda x: -x["run_count"])

        # Result-level aggregation requires inspecting stored per-test results JSON
        domain_agg: dict[str, dict[str, Any]] = {}
        retrieval_used = 0
        grounding_overlap = 0
        strict_rag_total = 0
        strict_rag_ok = 0
        # Helper to load results for a given run id
        if rows:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                run_ids = [r["id"] for r in rows]
                placeholders = ",".join("?" for _ in run_ids)
                cursor = conn.execute(
                    f"SELECT id, results FROM rag_test_runs WHERE id IN ({placeholders})",
                    run_ids,
                )
                result_rows = cursor.fetchall()
                results_by_id = {rr["id"]: rr["results"] for rr in result_rows}

            for r in rows:
                raw_results = results_by_id.get(r["id"])
                if not raw_results:
                    continue
                try:
                    tests = [normalize_rag_test_result(t) for t in json.loads(raw_results)]
                except (json.JSONDecodeError, TypeError):
                    continue
                for t in tests:
                    if t.get("retrieval_used"):
                        retrieval_used += 1
                    if t.get("grounding_overlap") is True:
                        grounding_overlap += 1
                    if t.get("strict_rag_ok") is not None:
                        strict_rag_total += 1
                        if t.get("strict_rag_ok") is True:
                            strict_rag_ok += 1
                    framework = (t.get("framework") or "").strip()
                    difficulty = (t.get("difficulty") or "").strip() or "unknown"
                    status = (t.get("status") or "").upper()
                    if framework.lower() in ("swiftui", "uikit"):
                        domain = framework
                    else:
                        # Everything else falls under generic Swift domain
                        domain = "Swift"
                    key = domain
                    if key not in domain_agg:
                        domain_agg[key] = {
                            "domain": key,
                            "total": 0,
                            "passed": 0,
                            "failed": 0,
                            "by_difficulty": {},
                        }
                    d_entry = domain_agg[key]
                    d_entry["total"] += 1
                    if status == "PASS":
                        d_entry["passed"] += 1
                    else:
                        d_entry["failed"] += 1
                    by_diff = d_entry["by_difficulty"].setdefault(
                        difficulty,
                        {"difficulty": difficulty, "total": 0, "passed": 0, "failed": 0},
                    )
                    by_diff["total"] += 1
                    if status == "PASS":
                        by_diff["passed"] += 1
                    else:
                        by_diff["failed"] += 1

        domains: list[dict[str, Any]] = []
        for key, data in sorted(domain_agg.items(), key=lambda x: x[0]):
            total_domain = data["total"]
            pass_rate_domain = round((data["passed"] / total_domain * 100), 1) if total_domain else 0.0
            by_diff_list: list[dict[str, Any]] = []
            for _, diff_data in sorted(data["by_difficulty"].items(), key=lambda x: x[0]):
                total_diff = diff_data["total"]
                pass_rate_diff = round((diff_data["passed"] / total_diff * 100), 1) if total_diff else 0.0
                diff_entry = {
                    "difficulty": diff_data["difficulty"],
                    "total": total_diff,
                    "passed": diff_data["passed"],
                    "failed": diff_data["failed"],
                    "pass_rate_pct": pass_rate_diff,
                }
                by_diff_list.append(diff_entry)
            domains.append({
                "domain": data["domain"],
                "total": total_domain,
                "passed": data["passed"],
                "failed": data["failed"],
                "pass_rate_pct": pass_rate_domain,
                "by_difficulty": by_diff_list,
            })

        return {
            "total_runs": total_runs,
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate_pct": pass_rate_pct,
            "retrieval_used": retrieval_used,
            "retrieval_rate_pct": round((retrieval_used / total_tests * 100), 1) if total_tests else 0.0,
            "grounding_overlap": grounding_overlap,
            "grounding_overlap_rate_pct": round((grounding_overlap / total_tests * 100), 1) if total_tests else 0.0,
            "strict_rag_total": strict_rag_total,
            "strict_rag_ok": strict_rag_ok,
            "strict_rag_ok_rate_pct": round((strict_rag_ok / strict_rag_total * 100), 1) if strict_rag_total else 0.0,
            "per_model": per_model,
            "domains": domains,
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
                results = [normalize_rag_test_result(t) for t in json.loads(row["results"])]
            except (json.JSONDecodeError, TypeError):
                pass
        return normalize_rag_test_run({
            "id": row["id"],
            "provider_id": row["provider_id"],
            "model": row["model"],
            "status": row["status"],
            "total": row["total"],
            "passed": row["passed"],
            "failed": row["failed"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "results": results,
        })

    def delete_runs(
        self,
        *,
        run_ids: list[str] | None = None,
        status: str | None = None,
        max_pass_rate_pct: float | None = None,
    ) -> int:
        """Delete runs by explicit ids and/or simple filters. Returns deleted row count."""
        conditions: list[str] = []
        params: list[Any] = []

        if run_ids:
            ids = [str(run_id).strip() for run_id in run_ids if str(run_id).strip()]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conditions.append(f"id IN ({placeholders})")
                params.extend(ids)

        if status and status.strip():
            conditions.append("status = ?")
            params.append(status.strip())

        if max_pass_rate_pct is not None:
            threshold = max(0.0, float(max_pass_rate_pct))
            # Treat total=0 as 0% passed so empty/cancelled runs can be matched if needed.
            conditions.append("(CASE WHEN total > 0 THEN (CAST(passed AS REAL) * 100.0 / total) ELSE 0.0 END) < ?")
            params.append(threshold)

        if not conditions:
            return 0

        where_sql = " AND ".join(f"({condition})" for condition in conditions)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"DELETE FROM rag_test_runs WHERE {where_sql}",
                params,
            )
            conn.commit()
            return int(cursor.rowcount or 0)


_rag_test_runs_repository: Optional[RagTestRunsRepository] = None


def get_rag_test_runs_repository(db_path: Optional[str] = None) -> RagTestRunsRepository:
    """Get or create global RagTestRunsRepository instance."""
    global _rag_test_runs_repository
    if _rag_test_runs_repository is None:
        if db_path is None:
            db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        _rag_test_runs_repository = RagTestRunsRepository(db_path)
    return _rag_test_runs_repository
