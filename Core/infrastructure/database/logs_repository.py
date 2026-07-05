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
            dt = dt.replace(hour=23, minute=59, second=59) if end else dt.replace(hour=0, minute=0, second=0)
    except ValueError:
        return s
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _row_to_log_dict(row: sqlite3.Row) -> dict[str, Any]:
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
    return log


def _build_logs_filter_query(
    *,
    session_id: str,
    include_system: bool,
    since_id: Optional[int] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    autocomplete_only: Optional[bool] = None,
) -> tuple[str, list[Any]]:
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

    return query, params


_PROXY_JOURNAL_CHAIN_KEY_SQL = """
COALESCE(
    NULLIF(json_extract(metadata, '$.journal_group_key'), ''),
    NULLIF('chain:' || json_extract(metadata, '$.trace_chain_id'), 'chain:'),
    NULLIF('chain:' || json_extract(metadata, '$.trace.request.trace_chain_id'), 'chain:'),
    NULLIF('chain:' || json_extract(metadata, '$.trace.request.client_request_id'), 'chain:'),
    NULLIF('chain:' || json_extract(metadata, '$.client_request_id'), 'chain:'),
    CASE
        WHEN NULLIF(trim(json_extract(metadata, '$.user_query')), '') IS NOT NULL THEN
            'query:' ||
            lower(COALESCE(json_extract(metadata, '$.proxy_backend'), '')) || ':' ||
            lower(COALESCE(
                NULLIF(json_extract(metadata, '$.requested_model'), ''),
                json_extract(metadata, '$.model'),
                ''
            )) || ':' ||
            lower(trim(json_extract(metadata, '$.user_query')))
    END,
    'row:' || CAST(id AS TEXT)
)
"""


def _build_proxy_journal_where(
    *,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> tuple[str, list[Any]]:
    query = "session_id = 'proxy' AND level = 'INFO' AND source = 'proxy'"
    params: list[Any] = []
    if from_date is not None:
        query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date is not None:
        query += " AND timestamp <= ?"
        params.append(to_date)
    return query, params


def _compact_journal_query(text: str) -> str:
    return " ".join(str(text or "").split()).strip().lower()[:500]


def build_proxy_journal_group_key(metadata: dict[str, Any] | None, *, row_id: int | None = None) -> str:
    """Resolve stable journal group key: agent chain id, else prompt+model, else row id."""
    meta = metadata if isinstance(metadata, dict) else {}

    stored = meta.get("journal_group_key")
    if stored is not None and str(stored).strip():
        return str(stored).strip()

    for key in ("trace_chain_id", "client_request_id"):
        value = meta.get(key)
        if value is not None and str(value).strip():
            return f"chain:{str(value).strip()}"

    trace = meta.get("trace")
    trace_request = trace.get("request") if isinstance(trace, dict) else {}
    if isinstance(trace_request, dict):
        for key in ("trace_chain_id", "client_request_id", "incoming_request_id"):
            value = trace_request.get(key)
            if value is not None and str(value).strip():
                return f"chain:{str(value).strip()}"

    raw_query = _compact_journal_query(meta.get("user_query") or "")
    if raw_query:
        backend = str(meta.get("proxy_backend") or "").strip().lower()
        model = str(meta.get("requested_model") or meta.get("model") or "").strip().lower()
        return f"query:{backend}:{model}:{raw_query}"

    if row_id is not None:
        return f"row:{row_id}"
    return ""


def extract_proxy_journal_chain_key(metadata: dict[str, Any] | None, *, row_id: int | None = None) -> str:
    """Backward-compatible alias for chain-only extraction used by upsert callers."""
    return build_proxy_journal_group_key(metadata, row_id=row_id)


def _upsert_lookup_params(group_key: str, metadata: dict[str, Any]) -> tuple[Any, ...]:
    raw_query = _compact_journal_query(metadata.get("user_query") or "")
    backend = str(metadata.get("proxy_backend") or "").strip().lower()
    model = str(metadata.get("requested_model") or metadata.get("model") or "").strip().lower()
    return (
        group_key,
        group_key,
        group_key,
        group_key,
        group_key,
        group_key,
        group_key,
        raw_query,
        backend,
        model,
    )


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

    def upsert_proxy_journal_log(
        self,
        *,
        message: str,
        metadata: dict[str, Any],
        trace_chain_id: str = "",
    ) -> int:
        """Insert or merge a proxy journal row by agent task group key."""
        metadata = dict(metadata)
        if trace_chain_id:
            metadata["trace_chain_id"] = trace_chain_id
        group_key = build_proxy_journal_group_key(metadata)
        if group_key:
            metadata["journal_group_key"] = group_key

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = None
            if group_key:
                existing = conn.execute(
                    """
                    SELECT id, timestamp, metadata FROM logs
                    WHERE session_id = 'proxy' AND source = 'proxy' AND level = 'INFO'
                      AND (
                        json_extract(metadata, '$.journal_group_key') = ?
                        OR (? LIKE 'chain:%' AND (
                          json_extract(metadata, '$.trace_chain_id') = substr(?, 7)
                          OR json_extract(metadata, '$.trace.request.trace_chain_id') = substr(?, 7)
                          OR json_extract(metadata, '$.trace.request.client_request_id') = substr(?, 7)
                        ))
                        OR (? LIKE 'query:%' AND (
                          json_extract(metadata, '$.journal_group_key') = ?
                          OR (
                            lower(trim(COALESCE(json_extract(metadata, '$.user_query'), ''))) = ?
                            AND lower(COALESCE(json_extract(metadata, '$.proxy_backend'), '')) = ?
                            AND lower(COALESCE(
                              NULLIF(json_extract(metadata, '$.requested_model'), ''),
                              json_extract(metadata, '$.model'),
                              ''
                            )) = ?
                          )
                        ))
                      )
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    _upsert_lookup_params(group_key, metadata),
                ).fetchone()
            if existing is not None:
                old_meta: dict[str, Any] = {}
                if existing["metadata"]:
                    try:
                        old_meta = json.loads(existing["metadata"])
                    except json.JSONDecodeError:
                        old_meta = {}
                step_count = int(old_meta.get("agent_step_count") or 1) + 1
                merged_trace_ids = list(old_meta.get("merged_trace_ids") or [])
                latest_trace_id = metadata.get("trace_id")
                if latest_trace_id and latest_trace_id not in merged_trace_ids:
                    merged_trace_ids.append(latest_trace_id)
                metadata["agent_step_count"] = step_count
                metadata["merged_trace_ids"] = merged_trace_ids[-128:]
                metadata["journal_group_key"] = group_key
                metadata["first_timestamp"] = old_meta.get("first_timestamp") or existing["timestamp"]
                conn.execute(
                    """
                    UPDATE logs
                    SET message = ?, metadata = ?
                    WHERE id = ?
                    """,
                    (message, json.dumps(metadata), existing["id"]),
                )
                conn.commit()
                return int(existing["id"])

            metadata.setdefault("agent_step_count", 1)
            merged_trace_ids = list(metadata.get("merged_trace_ids") or [])
            if metadata.get("trace_id") and metadata["trace_id"] not in merged_trace_ids:
                merged_trace_ids.append(metadata["trace_id"])
            metadata["merged_trace_ids"] = merged_trace_ids[-128:]
            cursor = conn.execute(
                """
                INSERT INTO logs (session_id, level, source, message, error_type, metadata)
                VALUES ('proxy', 'INFO', 'proxy', ?, NULL, ?)
                """,
                (message, json.dumps(metadata)),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_proxy_journal_groups(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return newest proxy journal rows grouped by agent trace chain."""
        if from_date is not None:
            from_date = _normalize_log_timestamp_bound(from_date, end=False)
        if to_date is not None:
            to_date = _normalize_log_timestamp_bound(to_date, end=True)

        safe_limit = max(1, int(limit or 50))
        safe_offset = max(0, int(offset or 0))
        where_clause, params = _build_proxy_journal_where(from_date=from_date, to_date=to_date)

        sql = f"""
            WITH filtered AS (
                SELECT id, {_PROXY_JOURNAL_CHAIN_KEY_SQL} AS chain_key
                FROM logs
                WHERE {where_clause}
            ),
            grouped AS (
                SELECT chain_key, MAX(id) AS latest_id, COUNT(*) AS step_count
                FROM filtered
                GROUP BY chain_key
            )
            SELECT l.*, g.step_count AS grouped_step_count
            FROM grouped g
            JOIN logs l ON l.id = g.latest_id
            ORDER BY g.latest_id DESC
            LIMIT ? OFFSET ?
        """  # nosec B608 -- where_clause from _build_proxy_journal_where; values are parameterized
        query_params = [*params, safe_limit, safe_offset]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, query_params).fetchall()
            logs: list[dict[str, Any]] = []
            for row in rows:
                log = _row_to_log_dict(row)
                grouped_step_count = int(row["grouped_step_count"] or 1)
                meta = log.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                    log["metadata"] = meta
                meta["agent_step_count"] = max(int(meta.get("agent_step_count") or 1), grouped_step_count)
                logs.append(log)
            return logs

    def count_proxy_journal_groups(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> int:
        """Count distinct agent trace chains in the proxy journal."""
        if from_date is not None:
            from_date = _normalize_log_timestamp_bound(from_date, end=False)
        if to_date is not None:
            to_date = _normalize_log_timestamp_bound(to_date, end=True)

        where_clause, params = _build_proxy_journal_where(from_date=from_date, to_date=to_date)
        sql = f"""
            WITH filtered AS (
                SELECT id, {_PROXY_JOURNAL_CHAIN_KEY_SQL} AS chain_key
                FROM logs
                WHERE {where_clause}
            )
            SELECT COUNT(DISTINCT chain_key) FROM filtered
        """  # nosec B608 -- where_clause from _build_proxy_journal_where; values are parameterized
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(sql, params).fetchone()
            return int(row[0]) if row is not None else 0

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
        offset: int = 0,
        newest_first: bool = False,
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
            offset: Skip this many rows after filters (ignored when since_id is set)
            newest_first: When True, return rows in id DESC order without reversing

        Returns:
            List of log dicts
        """
        if from_date is not None:
            from_date = _normalize_log_timestamp_bound(from_date, end=False)
        if to_date is not None:
            to_date = _normalize_log_timestamp_bound(to_date, end=True)

        safe_offset = max(0, int(offset or 0))

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            query, params = _build_logs_filter_query(
                session_id=session_id,
                include_system=include_system,
                since_id=since_id,
                level=level,
                source=source,
                from_date=from_date,
                to_date=to_date,
                autocomplete_only=autocomplete_only,
            )

            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            if since_id is None and safe_offset > 0:
                query += " OFFSET ?"
                params.append(safe_offset)

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            logs = [_row_to_log_dict(row) for row in rows]

            if not newest_first:
                logs.reverse()
            return logs

    def count_logs(
        self,
        session_id: str,
        level: Optional[str] = None,
        since_id: Optional[int] = None,
        source: Optional[str] = None,
        include_system: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        autocomplete_only: Optional[bool] = None,
    ) -> int:
        """Count log rows matching the same filters as ``get_logs``."""
        if from_date is not None:
            from_date = _normalize_log_timestamp_bound(from_date, end=False)
        if to_date is not None:
            to_date = _normalize_log_timestamp_bound(to_date, end=True)

        with sqlite3.connect(self.db_path) as conn:
            query, params = _build_logs_filter_query(
                session_id=session_id,
                include_system=include_system,
                since_id=since_id,
                level=level,
                source=source,
                from_date=from_date,
                to_date=to_date,
                autocomplete_only=autocomplete_only,
            )
            count_query = query.replace("SELECT *", "SELECT COUNT(*)", 1)
            row = conn.execute(count_query, params).fetchone()
            return int(row[0]) if row is not None else 0

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

