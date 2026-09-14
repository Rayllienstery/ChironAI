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
_live_completion_tokens: dict[str, int] = {}
_live_visible_previews: dict[str, tuple[str, bool]] = {}
_response_artifacts: dict[str, dict[str, Any]] = {}
_response_artifacts_updated: dict[str, datetime] = {}

_ACTIVE_TRACE_TTL = timedelta(seconds=45)
_COMPLETE_TRACE_GRACE = timedelta(seconds=2)
_RESPONSE_ARTIFACTS_TTL = timedelta(seconds=45)
_LIVE_VISIBLE_TAIL_CHARS = 200


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


def _drop_active_trace(key: str) -> None:
    _active_traces.pop(key, None)
    _active_trace_updated.pop(key, None)
    _live_completion_tokens.pop(key, None)
    _live_visible_previews.pop(key, None)


def _prune_active_traces(now: datetime) -> None:
    for key in list(_active_traces.keys()):
        updated = _active_trace_updated.get(key)
        if updated is None:
            _drop_active_trace(key)
            continue
        trace = _active_traces.get(key) or {}
        age = now - updated
        if age > _ACTIVE_TRACE_TTL or (_trace_complete(trace) and age > _COMPLETE_TRACE_GRACE):
            _drop_active_trace(key)


def _prune_response_artifacts(now: datetime) -> None:
    for key in list(_response_artifacts.keys()):
        updated = _response_artifacts_updated.get(key)
        if updated is None or (now - updated) > _RESPONSE_ARTIFACTS_TTL:
            _response_artifacts.pop(key, None)
            _response_artifacts_updated.pop(key, None)


def _int_or_none(value: Any) -> int | None:
    try:
        n = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return n


def _patch_live_token_estimates(
    tr: dict[str, Any],
    *,
    completion_tokens: int | None = None,
    prompt_tokens: int | None = None,
) -> None:
    ollama = tr.get("ollama")
    if not isinstance(ollama, dict):
        ollama = {}
        tr["ollama"] = ollama
    estimates = ollama.get("tokens_estimates")
    if not isinstance(estimates, dict):
        estimates = {}
        ollama["tokens_estimates"] = estimates
    ollama["chat_stream"] = True
    if prompt_tokens is not None:
        estimates["prompt_tokens_estimated"] = max(0, int(prompt_tokens))
    if completion_tokens is not None:
        estimates["completion_tokens_estimated"] = max(0, int(completion_tokens))
    prompt_n = _int_or_none(estimates.get("prompt_tokens_estimated"))
    completion_n = _int_or_none(estimates.get("completion_tokens_estimated"))
    if prompt_n is not None and completion_n is not None:
        estimates["total_tokens_estimated"] = prompt_n + completion_n


def _patch_live_completion_tokens(tr: dict[str, Any], completion_tokens: int) -> None:
    _patch_live_token_estimates(tr, completion_tokens=completion_tokens)


def _strip_live_preview_fields(tr: dict[str, Any]) -> None:
    for name in ("ollama", "provider"):
        bucket = tr.get(name)
        if isinstance(bucket, dict):
            bucket.pop("live_visible_tail", None)
            bucket.pop("live_visible_tail_truncated", None)


def _patch_live_visible_tail(tr: dict[str, Any], tail: str, truncated: bool) -> None:
    ollama = tr.get("ollama")
    if not isinstance(ollama, dict):
        ollama = {}
        tr["ollama"] = ollama
    ollama["live_visible_tail"] = str(tail or "")
    ollama["live_visible_tail_truncated"] = bool(truncated)


def _merge_live_visible_tail(tr: dict[str, Any] | None) -> None:
    if not isinstance(tr, dict):
        return
    preview = _live_visible_previews.get(_trace_key(tr))
    if preview is None:
        return
    _patch_live_visible_tail(tr, preview[0], preview[1])


def _normalize_visible_tail(visible_tail: str) -> tuple[str, bool]:
    raw = str(visible_tail or "")
    if len(raw) <= _LIVE_VISIBLE_TAIL_CHARS:
        return raw, False
    return raw[-_LIVE_VISIBLE_TAIL_CHARS:], True


def _estimated_completion_tokens(tr: dict[str, Any]) -> int | None:
    provider = tr.get("ollama") if isinstance(tr.get("ollama"), dict) else tr.get("provider")
    if not isinstance(provider, dict):
        return None
    estimates = provider.get("tokens_estimates")
    if not isinstance(estimates, dict):
        return None
    raw = estimates.get("completion_tokens_estimated")
    try:
        n = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
    return n if n is not None and n >= 0 else None


def _merge_live_progress(tr: dict[str, Any] | None) -> None:
    if not isinstance(tr, dict):
        return
    key = _trace_key(tr)
    live_n = _live_completion_tokens.get(key)
    if live_n is None:
        return
    existing = _estimated_completion_tokens(tr)
    tokens = live_n if existing is None else max(live_n, existing)
    _live_completion_tokens[key] = tokens
    _patch_live_completion_tokens(tr, tokens)


def update_live_stream_progress(
    *,
    trace_id: str | None = None,
    completion_tokens: int = 0,
    prompt_tokens: int | None = None,
    visible_tail: str | None = None,
    visible_tail_truncated: bool | None = None,
) -> None:
    """Patch live token counts and a short visible tail without growing the ring buffer.

    SSE generators call this ~5Hz so CoreUI can show tokens already sent without
    snapshotting every delta into Traces history.
    """
    global _updated_at
    tokens = max(0, int(completion_tokens))
    prompt_n = max(0, int(prompt_tokens)) if prompt_tokens is not None else None
    with _lock:
        now = datetime.now(timezone.utc)
        _updated_at = now.isoformat()
        tid = str(trace_id or "").strip()
        if tid:
            prev = _live_completion_tokens.get(tid, 0)
            _live_completion_tokens[tid] = max(prev, tokens)
            tokens = _live_completion_tokens[tid]
            if visible_tail is not None:
                tail, sliced = _normalize_visible_tail(visible_tail)
                truncated = bool(visible_tail_truncated) or sliced
                _live_visible_previews[tid] = (tail, truncated)
        if _current_trace is not None and (not tid or _trace_key(_current_trace) == tid):
            _patch_live_token_estimates(
                _current_trace,
                completion_tokens=tokens,
                prompt_tokens=prompt_n,
            )
            _merge_live_visible_tail(_current_trace)
        if tid:
            active = _active_traces.get(tid)
            if isinstance(active, dict):
                _patch_live_token_estimates(
                    active,
                    completion_tokens=tokens,
                    prompt_tokens=prompt_n,
                )
                _merge_live_visible_tail(active)
                _active_trace_updated[tid] = now
        _prune_active_traces(now)


def _patch_live_url_fetch_count(
    tr: dict[str, Any],
    url_fetch_count: int,
    url_fetch_urls: list[str] | None = None,
) -> None:
    n = max(0, int(url_fetch_count))
    if n <= 0:
        return
    request = tr.get("request")
    if not isinstance(request, dict):
        request = {}
        tr["request"] = request
    request["url_fetch_count"] = n
    internet = tr.get("internet")
    if not isinstance(internet, dict):
        internet = {}
        tr["internet"] = internet
    internet["url_fetch_count"] = n
    if isinstance(url_fetch_urls, list):
        stored = [str(u).strip() for u in url_fetch_urls if str(u or "").strip()]
        if stored:
            request["url_fetch_urls"] = stored
            internet["url_fetch_urls"] = list(stored)


def update_live_url_fetch_count(
    *,
    trace_id: str | None = None,
    url_fetch_count: int = 0,
    url_fetch_urls: list[str] | None = None,
) -> None:
    """Patch URL-fetch count onto the live card without a new ring-buffer snapshot."""
    n = max(0, int(url_fetch_count))
    if n <= 0:
        return
    with _lock:
        tid = str(trace_id or "").strip()
        if _current_trace is not None and (not tid or _trace_key(_current_trace) == tid):
            _patch_live_url_fetch_count(_current_trace, n, url_fetch_urls)
        if tid:
            active = _active_traces.get(tid)
            if isinstance(active, dict):
                _patch_live_url_fetch_count(active, n, url_fetch_urls)


def set_current_trace(trace: dict[str, Any] | None) -> None:
    """Set latest trace (thread-safe). Non-None snapshots are copied into the ring buffer."""
    global _current_trace, _updated_at
    with _lock:
        now = datetime.now(timezone.utc)
        _current_trace = trace
        _updated_at = now.isoformat()
        if trace is not None:
            _merge_live_progress(trace)
            ring_copy = copy.deepcopy(trace)
            _strip_live_preview_fields(ring_copy)
            _trace_buffer.append(ring_copy)
            active_copy = copy.deepcopy(trace)
            _merge_live_visible_tail(active_copy)
            _active_traces[_trace_key(active_copy)] = active_copy
            _active_trace_updated[_trace_key(active_copy)] = now
        _prune_active_traces(now)
        _prune_response_artifacts(now)


def get_current_trace() -> dict[str, Any] | None:
    """Get latest trace (thread-safe)."""
    with _lock:
        _merge_live_progress(_current_trace)
        _merge_live_visible_tail(_current_trace)
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
        out: list[dict[str, Any]] = []
        for _, trace in rows:
            copied = copy.deepcopy(trace)
            _merge_live_progress(copied)
            _merge_live_visible_tail(copied)
            out.append(copied)
        return out


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
        _live_completion_tokens.clear()
        _live_visible_previews.clear()
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
