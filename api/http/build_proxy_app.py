"""
Minimal Flask app exposing the same OpenAI-compatible /v1 routes as the main proxy.

Listens on a separate port (default 8087) for clients that want only build ids in GET /v1/models.
Uses the same wiring and blueprint as the main RAG proxy application.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)
_RAG_SVC = os.path.join(_ROOT, "CoreModules", "RagService")
if os.path.isdir(_RAG_SVC) and _RAG_SVC not in sys.path:
    sys.path.insert(0, _RAG_SVC)

from flask import Flask, jsonify

from application.rag.params import get_rag_answer_params
from api.http.llm_proxy_wiring import build_llm_proxy_wiring
from llm_proxy import create_v1_blueprint


def create_build_proxy_app(webui_dir: str | None = None) -> Flask:
    app = Flask(__name__)
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    wiring = build_llm_proxy_wiring(
        params=params,
        deps=deps,
        webui_dir=webui_dir,
        system_prefix=None,
        system_suffix=None,
    )
    app.extensions["llm_proxy_wiring"] = wiring
    app.register_blueprint(create_v1_blueprint(wiring))

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "build_proxy"})

    return app
