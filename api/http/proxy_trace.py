"""
In-memory store for the latest proxy/RAG trace.

Used by the WebUI "Proxy Trace" tab in Live mode.
History is persisted via logs metadata (see api/http/rag_routes.py).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()

_current_trace: dict[str, Any] | None = None
_updated_at: str | None = None


def set_current_trace(trace: dict[str, Any] | None) -> None:
    """Set latest trace (thread-safe)."""
    global _current_trace, _updated_at
    with _lock:
        _current_trace = trace
        _updated_at = datetime.now(timezone.utc).isoformat()


def get_current_trace() -> dict[str, Any] | None:
    """Get latest trace (thread-safe)."""
    with _lock:
        return _current_trace


def get_current_trace_updated_at() -> str | None:
    with _lock:
        return _updated_at

