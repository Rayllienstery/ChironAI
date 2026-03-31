"""Thread-safe current trace + bounded stream event buffer."""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from typing import Any

_MAX_STREAM_EVENTS = 8000

_lock = threading.Lock()
_current_trace: dict[str, Any] | None = None
_updated_at: str | None = None


def set_current_trace(trace: dict[str, Any] | None) -> None:
    global _current_trace, _updated_at
    with _lock:
        _current_trace = trace
        _updated_at = datetime.now(timezone.utc).isoformat()


def get_current_trace() -> dict[str, Any] | None:
    with _lock:
        if _current_trace is None:
            return None
        return copy.deepcopy(_current_trace)


def get_current_trace_updated_at() -> str | None:
    with _lock:
        return _updated_at


def new_trace(trace_id: str) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phases": [],
        "stream_events": [],
        "stream_truncated": False,
        "errors": [],
        "request": {},
        "upstream": {},
    }


def append_stream_line(trace: dict[str, Any], line: str) -> None:
    buf: list[str] = trace["stream_events"]  # type: ignore[assignment]
    if len(buf) >= _MAX_STREAM_EVENTS:
        trace["stream_truncated"] = True
        buf.pop(0)
    buf.append(line)


def phase(trace: dict[str, Any], name: str, **details: Any) -> None:
    phases = trace.setdefault("phases", [])
    phases.append({"name": name, **details})


def record_error(trace: dict[str, Any], message: str, tb: str | None) -> None:
    trace.setdefault("errors", []).append({"message": message, "traceback": tb})
