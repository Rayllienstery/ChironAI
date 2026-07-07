"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /, /health, /v1/* (via llm_proxy blueprint), and WebUI API routes.

Re-exports RAG/proxy symbols so tests can `monkeypatch.setattr(api.http.rag_routes, "build_rag_context", ...)`.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, Response

from core.bootstrap.import_paths import ensure_webui_composition_paths, ensure_webui_runtime_paths

_ROOT = ensure_webui_composition_paths()
ensure_webui_runtime_paths(_ROOT)

from rag_service.application.params import get_rag_answer_params
from rag_service.application.use_cases import build_rag_context, prepare_ollama_messages
from rag_service.domain.entities import RagContext, RagQuestionRequest
from rag_service.domain.services.prompt_builder import determine_reasoning_level, last_user_content

from application.rag.collection_freshness import check_collection_freshness
from infrastructure.database import get_logs_repository, get_session_manager, get_settings_repository
from infrastructure.logging import log_webui_error
from infrastructure.stack_health import check_stack_health
from llm_proxy import create_v1_blueprint
from prompts_manager import get_rag_system_prompt, rag_prompt_file_exists

try:
    from config import get_framework_collection_ttl_days, get_proxy_rerank_enabled, get_qdrant_url
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment,misc]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment,misc]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment,misc]

from api.http.extensions_service_access import (
    get_extensions_provider_registry,
    get_extensions_runtime,
    get_extensions_service,
    set_extensions_provider_registry,
    set_extensions_runtime,
    set_extensions_service,
)
from api.http.llm_proxy_wiring import build_llm_proxy_wiring


def _sync_llm_extension_runtime(app: Flask) -> bool:
    """Copy a background-bootstrapped LLM runtime into Flask extension state."""
    svc = get_extensions_service(app)
    runtime = getattr(svc, "runtime", None) if svc is not None else None
    registry = getattr(svc, "registry", None) if svc is not None else None
    changed = False
    if runtime is not None and get_extensions_runtime(app, svc) is not runtime:
        set_extensions_runtime(app, runtime)
        changed = True
    if registry is not None and get_extensions_provider_registry(app, svc) is not registry:
        set_extensions_provider_registry(app, registry)
        changed = True
    return changed


def _provider_health_component(app: Flask) -> str | None:
    svc = get_extensions_service(app)
    runtime = get_extensions_runtime(app, svc)
    if svc is None or runtime is None:
        return None

    try:
        rows = svc.provider_rows(runtime)
    except Exception:
        return "unhealthy"

    for row in rows or []:
        if str(row.get("provider_id") or "").strip() != "ollama":
            continue
        health = row.get("health") if isinstance(row.get("health"), dict) else {}
        return "healthy" if bool(health.get("ok")) else "unhealthy"
    return "unhealthy"


def _check_app_stack_health(app: Flask):
    return check_stack_health(provider_health_component=lambda: _provider_health_component(app))


def create_app(
    webui_dir: str | None = None,
    system_prefix: str | None = None,
    system_suffix: str | None = None,
    *,
    bootstrap_extensions: bool = True,
) -> Flask:
    """
    Create Flask app with RAG routes.
    webui_dir: directory containing last_collection.txt (e.g. Core/data/webui).
    system_prefix/suffix: optional overrides for RAG system prompt; if None use config (same as rag_client).
    bootstrap_extensions: when False, skip extension host bootstrap (OpenAPI/doc generation).
    """
    import time as _time

    from api.http.health_routes import register_health_routes
    from api.http.metrics_routes import register_metrics_routes
    from api.http.security_headers import register_security_headers
    from api.http.startup_timing import process_start_offset_ms, record_phase
    from infrastructure.observability import configure_flask_otel

    _t_app_start = _time.perf_counter()

    app = Flask(__name__)
    register_security_headers(app)
    register_metrics_routes(app)
    configure_flask_otel(app)

    _t_params_start = _time.perf_counter()
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    _params_ms = (_time.perf_counter() - _t_params_start) * 1000

    _t_wiring_start = _time.perf_counter()
    wiring = build_llm_proxy_wiring(
        params=params,
        deps=deps,
        webui_dir=webui_dir,
        system_prefix=system_prefix,
        system_suffix=system_suffix,
        bootstrap_extensions=bootstrap_extensions,
    )
    _wiring_ms = (_time.perf_counter() - _t_wiring_start) * 1000

    app.extensions["llm_proxy_wiring"] = wiring
    if getattr(wiring, "llm_runtime", None) is not None:
        set_extensions_runtime(app, wiring.llm_runtime)
    if getattr(wiring, "provider_registry", None) is not None:
        set_extensions_provider_registry(app, wiring.provider_registry)
    if getattr(wiring, "extension_manager", None) is not None:
        set_extensions_service(app, wiring.extension_manager)

    from rag_service.infrastructure.runtime_hooks import set_llm_runtime_getter

    from api.http.llm_runtime_access import resolve_llm_runtime

    def _app_llm_runtime() -> Any | None:
        svc = get_extensions_service(app)
        wiring_manager = getattr(wiring, "extension_manager", None)
        manager = svc if svc is not None else wiring_manager
        return resolve_llm_runtime(
            extension_manager=manager,
            llm_runtime=get_extensions_runtime(app, svc),
            sync_bootstrap=bootstrap_extensions,
        )

    set_llm_runtime_getter(_app_llm_runtime)

    extension_manager = getattr(wiring, "extension_manager", None)
    if bootstrap_extensions and extension_manager is not None:
        try:
            resolve_llm_runtime(extension_manager=extension_manager, sync_bootstrap=True)
            _sync_llm_extension_runtime(app)
        except Exception as exc:
            import logging

            logging.getLogger("trag.rag").warning("Startup LLM runtime bootstrap failed: %s", exc)

    _t_bp_start = _time.perf_counter()
    app.register_blueprint(create_v1_blueprint(wiring))
    from api.http.rag_tests_routes import rag_tests_bp
    from api.http.webui_routes import webui_bp
    from core.openapi import register_openapi_routes
    app.register_blueprint(webui_bp)
    app.register_blueprint(rag_tests_bp)
    register_health_routes(app, lambda: _check_app_stack_health(app))
    register_openapi_routes(app)
    _bp_ms = (_time.perf_counter() - _t_bp_start) * 1000

    _sync_llm_extension_runtime(app)

    _app_total_ms = (_time.perf_counter() - _t_app_start) * 1000
    record_phase(
        phase_id="flask_app_init",
        label="Flask App Init",
        description="Flask application creation, dependency wiring, and blueprint registration",
        start_offset_ms=process_start_offset_ms(_t_app_start),
        duration_ms=_app_total_ms,
        status="ok",
        steps=[
            {
                "id": "rag_params",
                "label": "RAG Answer Params",
                "description": "Load RAG answer parameters and dependencies",
                "start_offset_ms": process_start_offset_ms(_t_params_start),
                "duration_ms": round(_params_ms, 1),
                "status": "ok",
            },
            {
                "id": "llm_proxy_wiring",
                "label": "LLM Proxy Wiring",
                "description": "Build LlmProxyWiring: extension manager, provider registry, RAG deps",
                "start_offset_ms": process_start_offset_ms(_t_wiring_start),
                "duration_ms": round(_wiring_ms, 1),
                "status": "ok",
            },
            {
                "id": "blueprint_registration",
                "label": "Blueprint Registration",
                "description": "Register /v1/*, /api/webui/*, /rag-tests/* blueprints",
                "start_offset_ms": process_start_offset_ms(_t_bp_start),
                "duration_ms": round(_bp_ms, 1),
                "status": "ok",
            },
        ],
    )

    @app.before_request
    def _refresh_llm_extension_runtime() -> None:
        _sync_llm_extension_runtime(app)

    @app.route("/")
    def index() -> Response:
        """Redirect root to WebUI."""
        return Response(
            '<!DOCTYPE html><html><head><meta http-equiv="refresh" '
            'content="0; url=/webui"></head><body>'
            '<p>Redirecting to <a href="/webui">/webui</a>...</p>'
            "</body></html>",
            status=302,
            headers={"Location": "/webui"},
            mimetype="text/html; charset=utf-8",
        )

    return app


__all__ = [
    "RagContext",
    "RagQuestionRequest",
    "build_rag_context",
    "check_collection_freshness",
    "create_app",
    "determine_reasoning_level",
    "get_framework_collection_ttl_days",
    "get_logs_repository",
    "get_proxy_rerank_enabled",
    "get_qdrant_url",
    "get_rag_answer_params",
    "get_rag_system_prompt",
    "get_session_manager",
    "get_settings_repository",
    "last_user_content",
    "log_webui_error",
    "prepare_ollama_messages",
    "rag_prompt_file_exists",
]
