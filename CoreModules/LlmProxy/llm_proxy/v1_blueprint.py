"""Flask blueprint for OpenAI-compatible /v1 routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, jsonify, request

from llm_proxy.apply_edit import run_apply_file_edit
from llm_proxy.chat_completions import run_chat_completions
from llm_proxy.completions_generate import run_legacy_completions_via_ollama_generate
from llm_proxy.config import RAG_MODEL_ID
from llm_proxy.external_ingest import run_external_docs_ingest
from llm_proxy.ollama_upstream import forward_ollama_api
from llm_proxy.workspace import set_workspace_root

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring


def _post_body_is_openai_completions_shape(body: object) -> bool:
    """
    True when the client sent a legacy completions request (``prompt``/``input``)
    without a non-empty ``messages`` list — e.g. Zed edit prediction with API URL ending in ``/v1``.
    """
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


def create_v1_blueprint(wiring: LlmProxyWiring) -> Blueprint:
    """Register /v1/* routes; call `set_workspace_root` from `wiring.runtime`."""
    set_workspace_root(wiring.workspace_root)

    bp = Blueprint("llm_proxy_v1", __name__)

    @bp.route("/v1", methods=["GET", "POST"])
    def v1_root():
        # Some clients use …/v1 as the completions base URL (POST body has ``prompt``, no ``messages``).
        # Route that to Ollama /api/generate like ``POST /v1/completions``. Chat keeps ``messages``.
        if request.method == "POST":
            _raw = request.get_json(force=True, silent=True) or {}
            if _post_body_is_openai_completions_shape(_raw):
                return run_legacy_completions_via_ollama_generate(wiring)
            return run_chat_completions(wiring)
        return jsonify({"object": "api", "version": "v1"})

    @bp.route("/v1/models", methods=["GET"])
    def list_models():
        data: list[dict[str, object]] = [
            {
                "id": wiring.runtime.rag_model_logical_id,
                "object": "model",
                "created": 0,
                "owned_by": "local",
            }
        ]
        try:
            if wiring.get_autocomplete_ollama_model():
                data.append(
                    {
                        "id": wiring.runtime.autocomplete_model_logical_id,
                        "object": "model",
                        "created": 0,
                        "owned_by": "local",
                    }
                )
        except Exception:
            pass
        return jsonify({"object": "list", "data": data})

    @bp.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        return run_chat_completions(wiring)

    @bp.route("/v1/completions", methods=["POST"])
    def legacy_completions():
        """OpenAI legacy completions — native Ollama ``/api/generate`` (e.g. Zed edit prediction)."""
        return run_legacy_completions_via_ollama_generate(wiring)

    @bp.route("/api/tags", methods=["GET"])
    def ollama_tags_proxy():
        """Zed (Ollama provider) lists models via GET /api/tags — must hit upstream Ollama."""
        return forward_ollama_api(wiring, "tags")

    @bp.route("/api/show", methods=["POST"])
    def ollama_show_proxy():
        """Model details (e.g. supports_thinking); Zed calls POST /api/show."""
        return forward_ollama_api(wiring, "show")

    @bp.route("/api/generate", methods=["POST"])
    def ollama_generate_proxy():
        """Inline / legacy generate; some clients POST /api/generate."""
        return forward_ollama_api(wiring, "generate")

    @bp.route("/api/chat", methods=["POST"])
    def ollama_chat_proxy():
        """
        Transparent proxy to upstream Ollama /api/chat (same JSON body, including `think`).
        Use the proxy host as Zed's Ollama API URL together with /api/tags + /api/show above.
        """
        return forward_ollama_api(wiring, "chat")

    @bp.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit():
        return run_apply_file_edit(wiring)

    @bp.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest():
        return run_external_docs_ingest(wiring)

    return bp


__all__ = ["create_v1_blueprint", "RAG_MODEL_ID"]
