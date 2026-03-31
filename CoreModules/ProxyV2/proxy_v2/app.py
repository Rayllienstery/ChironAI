"""Flask application factory for Proxy V2 (port 8081)."""

from __future__ import annotations

import traceback
import uuid
from typing import Any

from flask import Flask, jsonify, request

from proxy_v2.chat_v1 import run_v1_chat_completions
from proxy_v2.completions_v1 import run_v1_completions
from proxy_v2.contracts import ProxyV2Wiring
from proxy_v2.ollama_forward import forward_ollama_segment
from proxy_v2.trace_store import new_trace, phase, record_error, set_current_trace


def _post_body_is_openai_completions_shape(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    messages = body.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        return False
    if body.get("prompt") is not None:
        return True
    if body.get("input"):
        return True
    return False


def create_pass_proxy_v2_app(w: ProxyV2Wiring) -> Flask:
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health() -> Any:
        return jsonify({"status": "ok", "service": "proxy_v2"})

    @app.route("/v1", methods=["GET", "POST"])
    def v1_root() -> Any:
        if request.method == "POST":
            raw = request.get_json(force=True, silent=True) or {}
            if _post_body_is_openai_completions_shape(raw):
                return run_v1_completions(w)
            return run_v1_chat_completions(w)
        return jsonify({"object": "api", "version": "v1"})

    @app.route("/v1/models", methods=["GET"])
    def list_models() -> Any:
        pinned = (w.get_pinned_model() or "").strip()
        data: list[dict[str, object]] = []
        if pinned:
            data.append({"id": pinned, "object": "model", "created": 0, "owned_by": "local"})
        return jsonify({"object": "list", "data": data})

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions() -> Any:
        return run_v1_chat_completions(w)

    @app.route("/v1/completions", methods=["POST"])
    def legacy_completions() -> Any:
        return run_v1_completions(w)

    @app.route("/api/tags", methods=["GET"])
    def ollama_tags_proxy() -> Any:
        return forward_ollama_segment(w, "tags")

    @app.route("/api/show", methods=["POST"])
    def ollama_show_proxy() -> Any:
        return forward_ollama_segment(w, "show")

    @app.route("/api/generate", methods=["POST"])
    def ollama_generate_proxy() -> Any:
        return forward_ollama_segment(w, "generate")

    @app.route("/api/chat", methods=["POST"])
    def ollama_chat_proxy() -> Any:
        return forward_ollama_segment(w, "chat")

    @app.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit() -> Any:
        tid = f"v2-{uuid.uuid4().hex[:12]}"
        tr = new_trace(tid)
        tr["request"]["path"] = request.path
        phase(tr, "host_delegate", route="apply-edit")
        set_current_trace(tr)
        fn = w.host_apply_file_edit
        if fn is None:
            record_error(tr, "apply-edit delegate not configured", None)
            set_current_trace(tr)
            return jsonify({"error": "apply-edit not configured on Proxy V2 host wiring"}), 503
        try:
            out = fn()
            phase(tr, "host_delegate_done")
            set_current_trace(tr)
            return out
        except Exception as e:
            record_error(tr, str(e), traceback.format_exc())
            set_current_trace(tr)
            return jsonify({"error": str(e)}), 500

    @app.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest() -> Any:
        tid = f"v2-{uuid.uuid4().hex[:12]}"
        tr = new_trace(tid)
        tr["request"]["path"] = request.path
        phase(tr, "host_delegate", route="external-docs/ingest")
        set_current_trace(tr)
        fn = w.host_external_docs_ingest
        if fn is None:
            record_error(tr, "external-docs ingest delegate not configured", None)
            set_current_trace(tr)
            return jsonify({"error": "external-docs ingest not configured on Proxy V2 host wiring"}), 503
        try:
            out = fn()
            phase(tr, "host_delegate_done")
            set_current_trace(tr)
            return out
        except Exception as e:
            record_error(tr, str(e), traceback.format_exc())
            set_current_trace(tr)
            return jsonify({"error": str(e)}), 500

    return app


__all__ = ["create_pass_proxy_v2_app"]
