"""Persist ClawCode agent traces to WebUI SQLite (same process as main app; WEBUI_DB_PATH)."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOG = logging.getLogger("clawcode.journal")

# Approximate cap for metadata JSON; trim steps if exceeded.
_METADATA_JSON_SOFT_CAP = 450_000


def _shrink_trace_payload(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    steps = out.get("steps")
    if not isinstance(steps, list):
        return out
    slim: list[dict[str, Any]] = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        copy = dict(s)
        for key in (
            "thinking_raw",
            "assistant_content_raw",
            "assistant_visible",
            "chunks_info",
        ):
            if key in copy and isinstance(copy[key], str) and len(copy[key]) > 8000:
                copy[key] = copy[key][:8000] + "\n…[truncated for DB size]"
                copy[f"{key}_truncated"] = True
        slim.append(copy)
    out["steps"] = slim
    fm = out.get("final_message")
    if isinstance(fm, dict) and isinstance(fm.get("content"), str):
        c = fm["content"]
        if len(c) > 24_000:
            fm = dict(fm)
            fm["content"] = c[:24_000] + "\n…[truncated for DB size]"
            fm["content_truncated"] = True
            out["final_message"] = fm
    out["metadata_shrunk"] = True
    return out


def persist_clawcode_trace_to_db(rec: dict[str, Any]) -> None:
    """
    Write one trace row to logs (session_id=clawcode, source=clawcode).
    Safe no-op if infrastructure is unavailable (standalone ClawCode test).
    """
    try:
        from infrastructure.database import get_logs_repository
        from infrastructure.database.session_manager import get_session_manager
    except ImportError:
        return

    try:
        get_session_manager().get_or_create_session("clawcode")
    except Exception:
        pass

    trace_id = str(rec.get("trace_id") or "")[:80]
    tid_short = trace_id[:8] if trace_id else "?"
    elapsed = rec.get("elapsed_ms")
    model = str(rec.get("resolved_model") or "")
    err = rec.get("error")
    line = f"ClawCode {tid_short} · {elapsed}ms · {model}"
    if err:
        line += f" · {err}"[:200]

    payload = dict(rec)
    try:
        blob = json.dumps(payload, ensure_ascii=False)
        if len(blob) > _METADATA_JSON_SOFT_CAP:
            payload = _shrink_trace_payload(payload)
            blob = json.dumps(payload, ensure_ascii=False)
        if len(blob) > _METADATA_JSON_SOFT_CAP:
            payload = {
                "trace_id": rec.get("trace_id"),
                "ts_ms": rec.get("ts_ms"),
                "error": "trace_too_large_for_db",
                "original_error": rec.get("error"),
                "resolved_model": rec.get("resolved_model"),
                "step_count": rec.get("step_count"),
            }
    except (TypeError, ValueError):
        payload = {"trace_id": trace_id, "error": "trace_json_encode_failed"}

    try:
        repo = get_logs_repository()
        repo.upsert_clawcode_journal_trace(line[:500], payload)
    except Exception:
        _LOG.exception("persist_clawcode_trace_to_db failed")
