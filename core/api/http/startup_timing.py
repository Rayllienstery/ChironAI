"""
In-memory startup timing registry.

Populated during server init by instrumentation points in rag_proxy.py,
rag_routes.py, and llm_interactor/manager.py.  Modelled after proxy_status.py
— a simple thread-safe module-level store with no external dependencies.

Usage::

    from api.http.startup_timing import record_phase, get_startup_report

    t0 = time.perf_counter()
    # ... do work ...
    record_phase(
        phase_id="session_manager",
        label="Session Manager",
        description="SQLite schema init and migrations",
        start_offset_ms=_offset(t0),
        duration_ms=(time.perf_counter() - t0) * 1000,
        status="ok",
    )
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()

# Epoch (time.time()) when the Python process began recording timing.
# Set on first record_phase call or explicitly via set_server_start_epoch.
_server_start_epoch_ms: float | None = None
_process_start_perf: float = time.perf_counter()  # reference point for offsets

# Ordered list of phase dicts.
_phases: list[dict[str, Any]] = []

# Browser timing submitted by the frontend (merged into the report).
_browser_timing: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------


def set_server_start_epoch(epoch_ms: float) -> None:
    """Override the recorded server-start wall-clock time (milliseconds since Unix epoch)."""
    global _server_start_epoch_ms
    with _lock:
        _server_start_epoch_ms = epoch_ms


def record_phase(
    phase_id: str,
    label: str,
    description: str,
    start_offset_ms: float,
    duration_ms: float,
    status: str,
    steps: list[dict[str, Any]] | None = None,
    log_lines: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append (or update) a startup phase record.

    Args:
        phase_id: Unique identifier (e.g. ``"flask_app_init"``).
        label: Human-readable name shown in the pipeline step.
        description: One-sentence description of what this phase does.
        start_offset_ms: Milliseconds after ``_process_start_perf`` when this
            phase began.
        duration_ms: Wall-clock time the phase took.
        status: ``"ok"`` | ``"failed"`` | ``"in_progress"`` | ``"skipped"``.
        steps: Optional list of sub-step dicts (same shape, no nested steps).
        log_lines: Optional list of raw log strings for the Debug Log view.
        metadata: Optional free-form key/value dict for extra context.
    """
    global _server_start_epoch_ms
    phase: dict[str, Any] = {
        "id": phase_id,
        "label": label,
        "description": description,
        "start_offset_ms": round(start_offset_ms, 1),
        "duration_ms": round(duration_ms, 1),
        "status": status,
        "steps": list(steps or []),
        "log_lines": list(log_lines or []),
        "metadata": dict(metadata or {}),
    }
    with _lock:
        if _server_start_epoch_ms is None:
            _server_start_epoch_ms = (time.time() * 1000) - start_offset_ms
        # Replace existing entry with the same id (allows updating in_progress → ok).
        for i, p in enumerate(_phases):
            if p["id"] == phase_id:
                _phases[i] = phase
                return
        _phases.append(phase)


def record_browser_timing(payload: dict[str, Any]) -> None:
    """Store browser Navigation Timing data submitted by the frontend."""
    global _browser_timing
    with _lock:
        _browser_timing = dict(payload)


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------


def get_startup_report() -> dict[str, Any]:
    """Return the full startup timing report as a JSON-serialisable dict."""
    with _lock:
        phases = [dict(p) for p in _phases]
        browser = dict(_browser_timing) if _browser_timing else None
        epoch_ms = _server_start_epoch_ms

    total_ms = sum(p["duration_ms"] for p in phases)
    return {
        "server_start_epoch_ms": epoch_ms,
        "total_duration_ms": round(total_ms, 1),
        "phases": phases,
        "browser_timing": browser,
    }


def process_start_offset_ms(perf_now: float | None = None) -> float:
    """Return milliseconds elapsed since the process reference point.

    Pass ``perf_now = time.perf_counter()`` captured *before* the phase begins
    to get the phase start offset.  Call without arguments at the *end* to get
    the current offset.
    """
    ref = perf_now if perf_now is not None else time.perf_counter()
    return (ref - _process_start_perf) * 1000.0


__all__ = [
    "get_startup_report",
    "process_start_offset_ms",
    "record_browser_timing",
    "record_phase",
    "set_server_start_epoch",
]
