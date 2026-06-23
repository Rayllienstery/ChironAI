"""
Current proxy task status for dashboard display.
Set by rag_routes and webui_routes during request handling.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_status: str = "idle"
_latest_request_seconds: float | None = None
_latest_request_total_tokens: int | None = None
_latest_request_rag_steps: dict[str, float] | None = None

STATUS_IDLE = "idle"
STATUS_RAG_SEARCH = "rag_search"
STATUS_PREPARING_RESPONSE = "preparing_response"
STATUS_RESPONSE = "response"


def set_proxy_status(status: str) -> None:
    global _status
    with _lock:
        _status = status


def get_proxy_status() -> str:
    with _lock:
        return _status


def get_proxy_status_label() -> str:
    """English label for UI."""
    s = get_proxy_status()
    return {
        STATUS_IDLE: "Idle",
        STATUS_RAG_SEARCH: "RAG search",
        STATUS_PREPARING_RESPONSE: "Preparing response",
        STATUS_RESPONSE: "Response",
    }.get(s, "Idle")


def set_latest_request_seconds(seconds: float) -> None:
    global _latest_request_seconds
    with _lock:
        _latest_request_seconds = seconds


def get_latest_request_seconds() -> float | None:
    with _lock:
        return _latest_request_seconds


def set_latest_request_total_tokens(total: int | None) -> None:
    global _latest_request_total_tokens
    with _lock:
        _latest_request_total_tokens = total


def get_latest_request_total_tokens() -> int | None:
    with _lock:
        return _latest_request_total_tokens


def set_latest_request_rag_steps(steps: dict[str, float] | None) -> None:
    global _latest_request_rag_steps
    with _lock:
        _latest_request_rag_steps = dict(steps) if steps else None


def get_latest_request_rag_steps() -> dict[str, float] | None:
    with _lock:
        return dict(_latest_request_rag_steps) if _latest_request_rag_steps else None
