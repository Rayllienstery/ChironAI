"""
Flask RAG API for rag_service.

Exposes /health, /v1/models, /v1/chat/completions. Run with project root on PYTHONPATH
so config and config.rag_prompts are available.
"""

from __future__ import annotations

import json
import logging
import uuid

from flask import Flask, Response, jsonify, request

from domain.entities.rag import RagQuestionRequest
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.stack_health import check_stack_health
from rag_service.application.params import get_rag_answer_params
from rag_service.application.use_cases import (
    answer_question,
    build_rag_context,
    prepare_ollama_messages,
)

_LOG = logging.getLogger("rag_service.api")


def create_app(
    webui_dir: str | None = None,
    system_prefix: str | None = None,
    system_suffix: str | None = None,
) -> Flask:
    """Create Flask app with RAG routes."""
    app = Flask(__name__)
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    prefix = system_prefix if system_prefix is not None else params.system_prefix
    suffix = system_suffix if system_suffix is not None else params.system_suffix
    context_chunk_chars = params.context_chunk_chars
    context_total_chars = params.context_total_chars
    confidence_threshold = params.confidence_threshold
    ollama_model = params.model_name
    rag_repo = deps.rag_repo
    embed_provider = deps.embed_provider
    rerank_client = deps.rerank_client
    chat_client = deps.chat_client

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        result = check_stack_health()
        return jsonify(result.to_json_dict(service="rag_service")), result.http_status

    @app.route("/v1/models", methods=["GET"])
    def list_models() -> Response:
        return jsonify({
            "object": "list",
            "data": [{"id": ollama_model, "object": "model", "created": 0, "owned_by": "local"}],
        })

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions() -> Response | tuple[Response, int]:
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            _LOG.error("parse_body: %s", e)
            return jsonify({"error": "Invalid JSON"}), 400
        messages = body.get("messages") or []
        stream = body.get("stream", False)
        raw_m = body.get("model")
        if raw_m is None or not str(raw_m).strip():
            return jsonify({"error": "model is required (use the Ollama tag from GET /v1/models)"}), 400
        requested_model = str(raw_m).strip()
        explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
        include_rag_metadata = body.get("include_rag_metadata", False)
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        last_user = last_user_content(messages)
        context_length = len(last_user.split())
        reasoning_level = determine_reasoning_level(
            last_user, context_length, ollama_model, explicit_reasoning
        )
        actual_model = requested_model
        rag_ctx_for_log = None
        rag_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
        try:
            rag_ctx_for_log, rag_timings = build_rag_context(
                last_user, rag_repo, embed_provider, rerank_client,
                context_chunk_chars, context_total_chars,
            )
        except Exception as e:
            _LOG.warning("build_rag_context failed: %s", e)
        req = RagQuestionRequest(
            messages=messages,
            model=actual_model,
            stream=stream,
            reasoning_level=reasoning_level,
        )
        try:
            ollama_messages, use_model = prepare_ollama_messages(
                req, rag_repo, embed_provider, rerank_client,
                prefix, suffix, context_chunk_chars, context_total_chars,
                confidence_threshold, ollama_model, reasoning_level=reasoning_level,
                rag_context=rag_ctx_for_log,
            )
        except Exception as e:
            _LOG.error("prepare_rag: %s", e)
            return jsonify({"error": str(e)}), 500
        if stream:
            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                try:
                    for content in chat_client.stream_chat(ollama_messages, use_model):
                        if content:
                            chunk = {
                                "id": oid,
                                "object": "chat.completion.chunk",
                                "model": use_model,
                                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as e:
                    _LOG.error("stream_chat: %s", e)
                    raise
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            answer = answer_question(
                req, rag_repo, embed_provider, rerank_client, chat_client,
                prefix, suffix, context_chunk_chars, context_total_chars,
                confidence_threshold, ollama_model, reasoning_level=reasoning_level,
                rag_context=rag_ctx_for_log,
            )
        except Exception as e:
            _LOG.error("chat: %s", e)
            return jsonify({"error": str(e)}), 500
        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": answer.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer.content},
                "finish_reason": answer.finish_reason,
            }],
        }
        if include_rag_metadata and rag_ctx_for_log:
            _rm: dict[str, object] = {
                "chunks_info": rag_ctx_for_log.chunks_info,
                "max_score": rag_ctx_for_log.max_score,
                "chunks_count": len(rag_ctx_for_log.chunks_info),
            }
            _rt = getattr(rag_ctx_for_log, "rag_trace", None)
            if isinstance(_rt, list):
                _rm["rag_trace"] = _rt
            _cr = getattr(rag_ctx_for_log, "coverage_report", None)
            if isinstance(_cr, dict):
                _rm["coverage_report"] = _cr
            _rq = getattr(rag_ctx_for_log, "rag_quality", None)
            if isinstance(_rq, dict):
                _rm["rag_quality"] = _rq
            response_data["rag_metadata"] = _rm
        return jsonify(response_data)

    return app


__all__ = ["create_app"]
