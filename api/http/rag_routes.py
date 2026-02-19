"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /v1/models, /v1/chat/completions, /, /v1, /health.
Uses application.rag.use_cases with wired dependencies from application.container.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid

from flask import Flask, Response, jsonify, request

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from application.rag.params import RAGDependencies, get_rag_answer_params
from application.rag.use_cases import answer_question, build_rag_context, prepare_ollama_messages
from domain.entities.rag import RagQuestionRequest
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.logging.webui_error_logger import log_webui_error

RAG_MODEL_ID = "rag-ollama"
_RAG_LOG = logging.getLogger("trag.rag")


def _log_rag_error(stage: str, error: Exception) -> None:
    """One-line console log: RAG stage=... | ErrorType: message."""
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


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
    prefix = system_prefix if system_prefix is not None else params.system_prefix
    suffix = system_suffix if system_suffix is not None else params.system_suffix
    context_chunk_chars = params.context_chunk_chars
    context_total_chars = params.context_total_chars
    confidence_threshold = params.confidence_threshold
    ollama_model = params.model_name
    log_preview = params.log_preview_chars
    rag_repo = deps.rag_repo
    embed_provider = deps.embed_provider
    rerank_client = deps.rerank_client
    chat_client = deps.chat_client

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

    @app.route("/v1", methods=["GET"])
    def v1_root() -> Response:
        return jsonify({"object": "api", "version": "v1"})

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/v1/models", methods=["GET"])
    def list_models() -> Response:
        return jsonify({
            "object": "list",
            "data": [{"id": RAG_MODEL_ID, "object": "model", "created": 0, "owned_by": "local"}],
        })

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions() -> Response | tuple[Response, int]:
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
            _log_rag_error("parse_body", e)
            return jsonify({"error": "Invalid JSON"}), 400
        messages = body.get("messages") or []
        stream = body.get("stream", False)
        model = body.get("model") or RAG_MODEL_ID
        explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
        include_rag_metadata = body.get("include_rag_metadata", False)
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        last_user = last_user_content(messages)
        context_length = len(last_user.split())
        reasoning_level = determine_reasoning_level(
            last_user, context_length, ollama_model, explicit_reasoning
        )
        
        # Build RAG context if metadata is requested
        rag_ctx = None
        if include_rag_metadata:
            try:
                rag_ctx = build_rag_context(
                    last_user,
                    rag_repo,
                    embed_provider,
                    rerank_client,
                    context_chunk_chars,
                    context_total_chars,
                )
            except Exception as e:
                _RAG_LOG.warning(f"Failed to build RAG context for metadata: {e}")
                rag_ctx = None
        try:
            req = RagQuestionRequest(
                messages=messages,
                model=model,
                stream=stream,
                reasoning_level=reasoning_level,
            )
            ollama_messages, use_model = prepare_ollama_messages(
                req,
                rag_repo,
                embed_provider,
                rerank_client,
                prefix,
                suffix,
                context_chunk_chars,
                context_total_chars,
                confidence_threshold,
                ollama_model,
                reasoning_level=reasoning_level,
            )
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
            _log_rag_error("prepare_rag", e)
            return jsonify({"error": str(e)}), 500
        if stream:
            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                preview = ""
                try:
                    for content in chat_client.stream_chat(ollama_messages, use_model):
                        if content:
                            preview += content[: max(0, log_preview - len(preview))]
                            chunk = {
                                "id": oid,
                                "object": "chat.completion.chunk",
                                "model": use_model,
                                "choices": [
                                    {"index": 0, "delta": {"content": content}, "finish_reason": None},
                                ],
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                    _RAG_LOG.info(
                        "RAG response (stream) model=%s len=%s preview=%s",
                        use_model,
                        len(preview),
                        preview[:log_preview] if preview else "",
                    )
                except Exception as e:
                    log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                    _log_rag_error("stream_chat", e)
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
                req,
                rag_repo,
                embed_provider,
                rerank_client,
                chat_client,
                prefix,
                suffix,
                context_chunk_chars,
                context_total_chars,
                confidence_threshold,
                ollama_model,
                reasoning_level=reasoning_level,
            )
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "chat"})
            _log_rag_error("chat", e)
            return jsonify({"error": str(e)}), 500
        content_len = len(answer.content or "")
        content_preview = (answer.content or "")[:log_preview]
        if content_len > log_preview:
            content_preview += "..."
        _RAG_LOG.info(
            "RAG response model=%s len=%s preview=%s",
            answer.model,
            content_len,
            content_preview,
        )
        choice = {
            "index": 0,
            "message": {"role": "assistant", "content": answer.content},
            "finish_reason": answer.finish_reason,
        }
        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": answer.model,
            "choices": [choice],
        }
        
        # Add RAG metadata if requested
        if include_rag_metadata and rag_ctx:
            response_data["rag_metadata"] = {
                "chunks_info": rag_ctx.chunks_info,
                "max_score": rag_ctx.max_score,
                "chunks_count": len(rag_ctx.chunks_info),
            }
        
        return jsonify(response_data)

    return app


__all__ = ["create_app"]
