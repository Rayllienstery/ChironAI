"""
In-memory store for the latest proxy/RAG trace and a ring buffer of recent snapshots.

Used by WebUI live notifications, GET /proxy-trace/current, and RAG Fusion Proxy → Traces.
History is persisted via logs metadata (see LlmProxy chat_completions).
"""

from __future__ import annotations

import copy
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

_lock = threading.Lock()

_current_trace: dict[str, Any] | None = None
_updated_at: str | None = None
_trace_buffer: deque[dict[str, Any]] = deque(maxlen=80)
_active_traces: dict[str, dict[str, Any]] = {}
_active_trace_updated: dict[str, datetime] = {}
_response_artifacts: dict[str, dict[str, Any]] = {}
_response_artifacts_updated: dict[str, datetime] = {}

_ACTIVE_TRACE_TTL = timedelta(seconds=45)
_COMPLETE_TRACE_GRACE = timedelta(seconds=2)
_RESPONSE_ARTIFACTS_TTL = timedelta(seconds=45)


def _trace_key(trace: dict[str, Any]) -> str:
    tid = str(trace.get("trace_id") or "").strip()
    if tid:
        return tid
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    chain = str(req.get("trace_chain_id") or "").strip()
    return chain or "unknown"


def _trace_complete(trace: dict[str, Any]) -> bool:
    resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
    if trace.get("error") is not None or resp.get("error") is not None:
        return True
    return resp.get("latency_ms") is not None


def _prune_active_traces(now: datetime) -> None:
    for key in list(_active_traces.keys()):
        updated = _active_trace_updated.get(key)
        if updated is None:
            _active_traces.pop(key, None)
            continue
        trace = _active_traces.get(key) or {}
        age = now - updated
        if age > _ACTIVE_TRACE_TTL or (_trace_complete(trace) and age > _COMPLETE_TRACE_GRACE):
            _active_traces.pop(key, None)
            _active_trace_updated.pop(key, None)


def _prune_response_artifacts(now: datetime) -> None:
    for key in list(_response_artifacts.keys()):
        updated = _response_artifacts_updated.get(key)
        if updated is None or (now - updated) > _RESPONSE_ARTIFACTS_TTL:
            _response_artifacts.pop(key, None)
            _response_artifacts_updated.pop(key, None)


def set_current_trace(trace: dict[str, Any] | None) -> None:
    """Set latest trace (thread-safe). Non-None snapshots are copied into the ring buffer."""
    global _current_trace, _updated_at
    with _lock:
        now = datetime.now(timezone.utc)
        _current_trace = trace
        _updated_at = now.isoformat()
        if trace is not None:
            trace_copy = copy.deepcopy(trace)
            _trace_buffer.append(trace_copy)
            _active_traces[_trace_key(trace_copy)] = trace_copy
            _active_trace_updated[_trace_key(trace_copy)] = now
        _prune_active_traces(now)
        _prune_response_artifacts(now)


def get_current_trace() -> dict[str, Any] | None:
    """Get latest trace (thread-safe)."""
    with _lock:
        return _current_trace


def get_current_trace_updated_at() -> str | None:
    with _lock:
        return _updated_at


def get_active_traces() -> list[dict[str, Any]]:
    """Get currently active live traces, oldest-updated first."""
    with _lock:
        _prune_active_traces(datetime.now(timezone.utc))
        rows = sorted(
            _active_traces.items(),
            key=lambda item: _active_trace_updated.get(item[0], datetime.min.replace(tzinfo=timezone.utc)),
        )
        return [copy.deepcopy(trace) for _, trace in rows]


def set_response_artifacts(
    *,
    trace_id: str | None = None,
    client_request_id: str | None = None,
    visible_content: str = "",
    reasoning_content: str = "",
    final_content: str = "",
) -> None:
    """Store short-lived separated response text artifacts for internal consumers."""
    keys = [
        str(k).strip()
        for k in (trace_id, client_request_id)
        if isinstance(k, str) and str(k).strip()
    ]
    if not keys:
        return
    payload = {
        "trace_id": str(trace_id or "").strip() or None,
        "client_request_id": str(client_request_id or "").strip() or None,
        "visible_content": str(visible_content or ""),
        "reasoning_content": str(reasoning_content or ""),
        "final_content": str(final_content or ""),
    }
    with _lock:
        now = datetime.now(timezone.utc)
        for key in keys:
            _response_artifacts[key] = copy.deepcopy(payload)
            _response_artifacts_updated[key] = now
        _prune_active_traces(now)
        _prune_response_artifacts(now)


def get_response_artifacts(key: str | None) -> dict[str, Any] | None:
    """Get separated response text artifacts by client_request_id or trace_id."""
    lookup = str(key or "").strip()
    if not lookup:
        return None
    with _lock:
        now = datetime.now(timezone.utc)
        _prune_active_traces(now)
        _prune_response_artifacts(now)
        payload = _response_artifacts.get(lookup)
        return copy.deepcopy(payload) if isinstance(payload, dict) else None


def _recent_raw(limit: int) -> list[dict[str, Any]]:
    with _lock:
        items = list(_trace_buffer)
    return items[-max(1, limit) :]


def recent_proxy_traces(limit: int = 40) -> list[dict[str, Any]]:
    """Oldest-first slice of the last ``limit`` buffered in-memory trace snapshots."""
    return _recent_raw(limit)


def clear_proxy_trace_buffer() -> None:
    with _lock:
        _trace_buffer.clear()
        _response_artifacts.clear()
        _response_artifacts_updated.clear()


def annotate_proxy_trace_for_ui(tr: dict[str, Any]) -> dict[str, Any]:
    """
    Copy trace and add top-level fields used by the WebUI Traces tab and ``summarizeAgentTraceMeta`` (CoreUI).
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
