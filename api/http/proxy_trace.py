"""
In-memory store for the latest proxy/RAG trace and a ring buffer of recent snapshots.

Used by WebUI live notifications, GET /proxy-trace/current, and RAG Fusion Proxy → Traces.
History is persisted via logs metadata (see LlmProxy chat_completions).
"""

from __future__ import annotations

import copy
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()

_current_trace: dict[str, Any] | None = None
_updated_at: str | None = None
_trace_buffer: deque[dict[str, Any]] = deque(maxlen=80)


def set_current_trace(trace: dict[str, Any] | None) -> None:
    """Set latest trace (thread-safe). Non-None snapshots are copied into the ring buffer."""
    global _current_trace, _updated_at
    with _lock:
        _current_trace = trace
        _updated_at = datetime.now(timezone.utc).isoformat()
        if trace is not None:
            _trace_buffer.append(copy.deepcopy(trace))


def get_current_trace() -> dict[str, Any] | None:
    """Get latest trace (thread-safe)."""
    with _lock:
        return _current_trace


def get_current_trace_updated_at() -> str | None:
    with _lock:
        return _updated_at


def _recent_raw(limit: int) -> list[dict[str, Any]]:
    with _lock:
        items = list(_trace_buffer)
    return items[-max(1, limit) :]


def recent_proxy_traces(limit: int = 40) -> list[dict[str, Any]]:
    """Oldest-first slice of the last ``limit`` buffered snapshots (matches Claw trace_store.recent)."""
    return _recent_raw(limit)


def clear_proxy_trace_buffer() -> None:
    with _lock:
        _trace_buffer.clear()


def annotate_proxy_trace_for_ui(tr: dict[str, Any]) -> dict[str, Any]:
    """
    Copy trace and add Claw-compatible top-level fields for Traces tab summary / summarizeClawTraceMeta.
    """
    out = dict(tr)
    req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
    steps = tr.get("steps") if isinstance(tr.get("steps"), list) else []
    resp = tr.get("response") if isinstance(tr.get("response"), dict) else {}
    ollama = tr.get("ollama") if isinstance(tr.get("ollama"), dict) else {}

    out["step_count"] = len(steps)
    lat = resp.get("latency_ms")
    if lat is not None:
        try:
            out["elapsed_ms"] = int(lat)
        except (TypeError, ValueError):
            out["elapsed_ms"] = sum(
                int(s.get("duration_ms") or 0) for s in steps if isinstance(s, dict)
            )
    else:
        out["elapsed_ms"] = sum(
            int(s.get("duration_ms") or 0) for s in steps if isinstance(s, dict)
        )

    am = req.get("actual_model")
    rm = req.get("requested_model")
    out["resolved_model"] = str(am or rm or ollama.get("model") or "")

    err = tr.get("error")
    if err is None and resp.get("error") is not None:
        err = resp.get("error")
    if err is not None:
        out["error"] = str(err)
    return out
