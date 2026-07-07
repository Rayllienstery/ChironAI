"""Production WSGI app factory for the ChironAI WebUI backend."""

from __future__ import annotations

import logging
import time as _time

from flask import Flask

from api.http.startup_timing import process_start_offset_ms, record_phase

_logger = logging.getLogger(__name__)


def create_production_app(
    webui_dir: str | None = None,
    *,
    bootstrap_extensions: bool = True,
    warm_session: bool = True,
    frontend_dir: str | None = None,
) -> Flask:
    """
    Build the full production Flask app: RAG/API routes, CoreUI static host, optional session warmup.

    This is the canonical factory used by ``start_webui.bat`` and ``python -m webui_backend.rag_proxy``.
    """
    from api.http.rag_routes import create_app
    from webui_backend.paths import coreui_dir, webui_data_dir
    from webui_backend.static_routes import register_webui_static_routes

    base_dir = webui_dir or str(webui_data_dir())
    app = create_app(
        webui_dir=base_dir,
        bootstrap_extensions=bootstrap_extensions,
    )
    register_webui_static_routes(
        app,
        frontend_dir=frontend_dir or str(coreui_dir()),
    )
    if warm_session:
        _warm_session_manager()
    return app


def _warm_session_manager() -> None:
    """Pre-warm SessionManager so the first /api/webui/sessions request is fast."""
    _t_session = _time.perf_counter()
    _session_status = "ok"
    try:
        from infrastructure.database import get_session_manager

        get_session_manager()
    except Exception:
        _session_status = "failed"
        _logger.debug("Session manager warmup failed", exc_info=True)
    _session_ms = (_time.perf_counter() - _t_session) * 1000
    record_phase(
        phase_id="session_manager",
        label="Session Manager",
        description="SQLite schema initialisation, migrations, and session table setup",
        start_offset_ms=process_start_offset_ms(_t_session),
        duration_ms=_session_ms,
        status=_session_status,
    )


__all__ = ["create_production_app"]
