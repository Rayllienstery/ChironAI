"""Flask blueprint for OpenAI-compatible /v1 routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, jsonify

from llm_proxy.apply_edit import run_apply_file_edit
from llm_proxy.chat_completions import run_chat_completions
from llm_proxy.config import RAG_MODEL_ID
from llm_proxy.edit_state import configure_ttl
from llm_proxy.external_ingest import run_external_docs_ingest
from llm_proxy.workspace import set_workspace_root

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring


def create_v1_blueprint(wiring: LlmProxyWiring) -> Blueprint:
    """Register /v1/* routes; call `set_workspace_root` and TTL from `wiring.runtime`."""
    set_workspace_root(wiring.workspace_root)
    configure_ttl(wiring.runtime.recent_success_ttl_s, wiring.runtime.recent_noop_ttl_s)

    bp = Blueprint("llm_proxy_v1", __name__)

    @bp.route("/v1", methods=["GET"])
    def v1_root():
        return jsonify({"object": "api", "version": "v1"})

    @bp.route("/v1/models", methods=["GET"])
    def list_models():
        return jsonify(
            {
                "object": "list",
                "data": [
                    {
                        "id": wiring.runtime.rag_model_logical_id,
                        "object": "model",
                        "created": 0,
                        "owned_by": "local",
                    }
                ],
            }
        )

    @bp.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        return run_chat_completions(wiring)

    @bp.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit():
        return run_apply_file_edit(wiring)

    @bp.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest():
        return run_external_docs_ingest(wiring)

    return bp


__all__ = ["create_v1_blueprint", "RAG_MODEL_ID"]
