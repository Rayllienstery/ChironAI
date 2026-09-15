"""Reset Windows display/sleep idle timers without holding the PC awake.

ChironAI itself must not assert ES_CONTINUOUS. RAG Fusion Proxy generation
requests pulse SetThreadExecutionState(ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
so the configured display and sleep countdowns restart, including a heartbeat
while the request (and any SSE body) is still in flight.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

from flask import Flask, g, request

_LOG = logging.getLogger("webui")

# Pulse often enough that a 10-minute display timeout cannot fire mid-generation.
_PULSE_INTERVAL_SEC = 60.0

_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

_GENERATION_PATHS = frozenset(
    {
        "/v1",
        "/v1/chat/completions",
        "/v1/messages",
        "/v1/responses",
    }
)

_lock = threading.Lock()
_inflight = 0
_generation = 0
_stop = threading.Event()
_thread: threading.Thread | None = None


def pulse_idle_timers() -> None:
    """Restart Windows display and sleep idle countdowns; do not hold them."""
    if sys.platform != "win32":
        return
    try:  # pragma: no cover - SetThreadExecutionState
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(_ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
    except Exception:
        _LOG.debug("Windows idle pulse failed", exc_info=True)


def is_rag_fusion_generation_request(method: str, path: str) -> bool:
    """True for RAG Fusion Proxy generation POSTs, not model-list polls."""
    if str(method or "").upper() != "POST":
        return False
    normalized = str(path or "").split("?", 1)[0].rstrip("/") or "/"
    return normalized in _GENERATION_PATHS


class _IdlePulseToken:
    """Idempotent end() so close + teardown cannot double-decrement."""

    def __init__(self) -> None:
        self._done = False
        self._done_lock = threading.Lock()

    def end(self) -> None:
        with self._done_lock:
            if self._done:
                return
            self._done = True
        end_proxy_activity()


def begin_proxy_activity() -> None:
    """Start (or join) the in-flight heartbeat and pulse immediately."""
    global _inflight, _thread, _generation
    pulse_idle_timers()
    with _lock:
        _inflight += 1
        if _inflight == 1:
            _stop.clear()
            _generation += 1
            my_generation = _generation
            _thread = threading.Thread(
                target=_heartbeat_loop,
                args=(my_generation,),
                name="chiron-idle-pulse",
                daemon=True,
            )
            _thread.start()


def end_proxy_activity() -> None:
    """Stop the heartbeat when the last in-flight request finishes, then pulse once more."""
    global _inflight
    with _lock:
        if _inflight > 0:
            _inflight -= 1
        if _inflight == 0:
            _stop.set()
    pulse_idle_timers()


def _heartbeat_loop(my_generation: int) -> None:
    while not _stop.wait(_PULSE_INTERVAL_SEC):
        with _lock:
            if my_generation != _generation or _inflight == 0:
                return
        pulse_idle_timers()


def register_rag_fusion_idle_pulses(app: Flask) -> None:
    """Nudge Windows idle timers while RAG Fusion Proxy generation is in flight."""

    @app.before_request
    def _begin_rag_fusion_idle_pulse() -> None:
        if not is_rag_fusion_generation_request(request.method, request.path):
            return
        begin_proxy_activity()
        g.chiron_idle_token = _IdlePulseToken()
        g.chiron_idle_hooked = False

    @app.after_request
    def _attach_rag_fusion_idle_pulse_end(response: Any) -> Any:
        token = getattr(g, "chiron_idle_token", None)
        if token is None:
            return response
        g.chiron_idle_hooked = True
        closer = getattr(response, "call_on_close", None)
        if callable(closer):
            closer(token.end)
        else:
            token.end()
        return response

    @app.teardown_request
    def _end_rag_fusion_idle_pulse_if_unhooked(_exc: BaseException | None) -> None:
        token = getattr(g, "chiron_idle_token", None)
        if token is not None and not getattr(g, "chiron_idle_hooked", False):
            token.end()
