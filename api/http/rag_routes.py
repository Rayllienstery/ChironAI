"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /, /health, /v1/* (via llm_proxy blueprint), and WebUI API routes.

Re-exports RAG/proxy symbols so tests can `monkeypatch.setattr(api.http.rag_routes, "build_rag_context", ...)`.
"""

from __future__ import annotations

import os
import sys

from typing import Any

from flask import Flask, Response, jsonify

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)
_RAG_SVC = os.path.join(_ROOT, "CoreModules", "RagService")
if os.path.isdir(_RAG_SVC) and _RAG_SVC not in sys.path:
    sys.path.insert(0, _RAG_SVC)
_DOCKER_MANAGER = os.path.join(_ROOT, "CoreModules", "DockerManager")
if os.path.isdir(_DOCKER_MANAGER) and _DOCKER_MANAGER not in sys.path:
    sys.path.insert(0, _DOCKER_MANAGER)
_LLM_INTERACTOR = os.path.join(_ROOT, "CoreModules", "LlmInteractor")
if os.path.isdir(_LLM_INTERACTOR) and _LLM_INTERACTOR not in sys.path:
    sys.path.insert(0, _LLM_INTERACTOR)
_SECURITY = os.path.join(_ROOT, "CoreModules", "Security")
if os.path.isdir(_SECURITY) and _SECURITY not in sys.path:
    sys.path.insert(0, _SECURITY)
_EXTENSIONS_SANDBOX = os.path.join(_ROOT, "CoreModules", "ExtensionsSandbox")
if os.path.isdir(_EXTENSIONS_SANDBOX) and _EXTENSIONS_SANDBOX not in sys.path:
    sys.path.insert(0, _EXTENSIONS_SANDBOX)
_EXTENSIONS_BACKEND = os.path.join(_ROOT, "modules", "extensions_backend")
if os.path.isdir(_EXTENSIONS_BACKEND) and _EXTENSIONS_BACKEND not in sys.path:
    sys.path.insert(0, _EXTENSIONS_BACKEND)
_ERROR_MANAGER = os.path.join(_ROOT, "CoreModules", "ErrorManager")
if os.path.isdir(_ERROR_MANAGER) and _ERROR_MANAGER not in sys.path:
    sys.path.insert(0, _ERROR_MANAGER)

from application.rag.collection_freshness import check_collection_freshness
from config.rag_prompts import get_rag_system_prompt, rag_prompt_file_exists
from infrastructure.database import get_logs_repository, get_session_manager, get_settings_repository
from infrastructure.logging import log_webui_error
from infrastructure.stack_health import check_stack_health
from llm_proxy import create_v1_blueprint
from rag_service.application.params import get_rag_answer_params
from rag_service.application.use_cases import build_rag_context, prepare_ollama_messages
from rag_service.domain.entities import RagContext, RagQuestionRequest
from rag_service.domain.services.prompt_builder import determine_reasoning_level, last_user_content

try:
    from config import get_framework_collection_ttl_days, get_proxy_rerank_enabled, get_qdrant_url
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment,misc]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment,misc]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment,misc]

from api.http.llm_proxy_wiring import build_llm_proxy_wiring
from api.http.extensions_service_access import (
    get_extensions_provider_registry,
    get_extensions_runtime,
    get_extensions_service,
    set_extensions_provider_registry,
    set_extensions_runtime,
    set_extensions_service,
)


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


def create_app(
    webui_dir: str | None = None,
    system_prefix: str | None = None,
    system_suffix: str | None = None,
) -> Flask:
    """
    Create Flask app with RAG routes.
    webui_dir: directory containing last_collection.txt (e.g. WebUI).
    system_prefix/suffix: optional overrides for RAG system prompt; if None use config (same as rag_client).
    """
    import time as _time
    from api.http.startup_timing import process_start_offset_ms, record_phase

    _t_app_start = _time.perf_counter()

    app = Flask(__name__)

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
    )
    _wiring_ms = (_time.perf_counter() - _t_wiring_start) * 1000

    app.extensions["llm_proxy_wiring"] = wiring
    if getattr(wiring, "llm_runtime", None) is not None:
        set_extensions_runtime(app, wiring.llm_runtime)
    if getattr(wiring, "provider_registry", None) is not None:
        set_extensions_provider_registry(app, wiring.provider_registry)
    if getattr(wiring, "extension_manager", None) is not None:
        set_extensions_service(app, wiring.extension_manager)

    from api.http.llm_runtime_access import resolve_llm_runtime
    from rag_service.infrastructure.runtime_hooks import set_llm_runtime_getter

    def _app_llm_runtime() -> Any | None:
        svc = get_extensions_service(app)
        wiring_manager = getattr(wiring, "extension_manager", None)
        manager = svc if svc is not None else wiring_manager
        return resolve_llm_runtime(
            extension_manager=manager,
            llm_runtime=get_extensions_runtime(app, svc),
            sync_bootstrap=True,
        )

    set_llm_runtime_getter(_app_llm_runtime)

    extension_manager = getattr(wiring, "extension_manager", None)
    if extension_manager is not None:
        try:
            from api.http.llm_runtime_access import resolve_llm_runtime

            resolve_llm_runtime(extension_manager=extension_manager, sync_bootstrap=True)
            _sync_llm_extension_runtime(app)
        except Exception as exc:
            import logging

            logging.getLogger("trag.rag").warning("Startup LLM runtime bootstrap failed: %s", exc)

    _t_bp_start = _time.perf_counter()
    app.register_blueprint(create_v1_blueprint(wiring))
    from api.http.webui_routes import webui_bp
    from api.http.rag_tests_routes import rag_tests_bp
    app.register_blueprint(webui_bp)
    app.register_blueprint(rag_tests_bp)
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

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        """Health check endpoint for Ollama and Qdrant availability."""
        result = check_stack_health()
        return jsonify(result.to_json_dict(service="rag_proxy")), result.http_status

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
