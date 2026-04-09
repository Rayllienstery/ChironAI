"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /, /health, /v1/* (via llm_proxy blueprint), and WebUI API routes.

Re-exports RAG/proxy symbols so tests can `monkeypatch.setattr(api.http.rag_routes, "build_rag_context", ...)`.
"""

from __future__ import annotations

import os
import sys

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

from application.rag.collection_freshness import check_collection_freshness
from application.rag.params import get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from config.rag_prompts import get_rag_system_prompt, rag_prompt_file_exists
from domain.entities.rag import RagContext, RagQuestionRequest
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.database import get_logs_repository, get_session_manager, get_settings_repository
from infrastructure.logging import log_webui_error
from llm_proxy import create_v1_blueprint

try:
    from config import get_framework_collection_ttl_days, get_proxy_rerank_enabled, get_qdrant_url
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment,misc]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment,misc]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment,misc]

from api.http.llm_proxy_wiring import build_llm_proxy_wiring


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
    app = Flask(__name__)
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    wiring = build_llm_proxy_wiring(
        params=params,
        deps=deps,
        webui_dir=webui_dir,
        system_prefix=system_prefix,
        system_suffix=system_suffix,
    )
    app.extensions["llm_proxy_wiring"] = wiring
    app.register_blueprint(create_v1_blueprint(wiring))

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
        return jsonify({"status": "ok"})

    from api.http.webui_routes import (
        open_webui_config,
        open_webui_status,
        open_webui_start,
        open_webui_stop,
        webui_bp,
    )

    app.add_url_rule(
        "/api/webui/open-webui/status",
        view_func=open_webui_status,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/config",
        view_func=open_webui_config,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/start",
        view_func=open_webui_start,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/stop",
        view_func=open_webui_stop,
        methods=["POST"],
    )

    app.register_blueprint(webui_bp)

    try:
        from api.http.clawcode_webui import register_clawcode_webui

        register_clawcode_webui(app)
    except ImportError:
        pass

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
