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
from infrastructure.database import get_session_manager, get_logs_repository
from api.http.proxy_status import (
    set_proxy_status,
    set_latest_request_seconds,
    set_latest_request_total_tokens,
    set_latest_request_rag_steps,
    STATUS_IDLE,
    STATUS_RAG_SEARCH,
    STATUS_PREPARING_RESPONSE,
    STATUS_RESPONSE,
)
import time

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
        start_time = time.time()
        user_query = ""
        rag_context_data = None
        response_content = ""
        latency_ms = 0
        prompt_tokens_approx = 0
        completion_tokens_approx = 0
        
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
            _log_rag_error("parse_body", e)
            return jsonify({"error": "Invalid JSON"}), 400
        messages = body.get("messages") or []
        stream = body.get("stream", False)
        requested_model = body.get("model") or RAG_MODEL_ID
        explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
        include_rag_metadata = body.get("include_rag_metadata", False)
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        set_proxy_status(STATUS_RAG_SEARCH)
        last_user = last_user_content(messages)
        user_query = last_user  # Store for logging
        context_length = len(last_user.split())
        reasoning_level = determine_reasoning_level(
            last_user, context_length, ollama_model, explicit_reasoning
        )
        
        # If model is "rag-ollama", use config model instead (rag-ollama is just a proxy identifier)
        actual_model = ollama_model if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID else requested_model
        
        # NOTE: RAG is ALWAYS used in this proxy endpoint.
        # Both prepare_ollama_messages() and answer_question() internally call build_rag_context()
        # to retrieve relevant context from the RAG database and include it in the system prompt.
        # There is no way to bypass RAG when using this proxy endpoint.
        
        # Proxy: do not read settings from DB here so RAG never fails (e.g. DB path differs).
        # RAG always runs (embed + search); rerank is off for proxy. Use WebUI /chat for rerank + settings.
        effective_rerank_client = None
        
        # Build RAG context for logging (always, not just for metadata)
        rag_ctx_for_log = None
        rag_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
        try:
            rag_ctx_for_log, rag_timings = build_rag_context(
                last_user,
                rag_repo,
                embed_provider,
                effective_rerank_client,
                context_chunk_chars,
                context_total_chars,
            )
            if rag_timings:
                set_latest_request_rag_steps(rag_timings)
                _RAG_LOG.info(
                    "RAG steps embed_s=%.2f search_s=%.2f rerank_s=%.2f total_rag_s=%.2f",
                    rag_timings.get("embed_s", 0),
                    rag_timings.get("search_s", 0),
                    rag_timings.get("rerank_s", 0),
                    rag_timings.get("total_rag_s", 0),
                )
            rag_context_data = {
                "chunks_count": len(rag_ctx_for_log.chunks_info),
                "max_score": rag_ctx_for_log.max_score,
                "context_length": len(rag_ctx_for_log.context_text),
                "chunks_info": rag_ctx_for_log.chunks_info[:5] if rag_ctx_for_log.chunks_info else [],  # First 5 chunks for preview
            }
        except Exception as e:
            _RAG_LOG.warning(f"Failed to build RAG context for logging: {e}")
            rag_context_data = None
        set_proxy_status(STATUS_PREPARING_RESPONSE)
        
        # Build RAG context if metadata is requested (for response metadata only)
        # Note: This is separate from the RAG context used in prepare_ollama_messages/answer_question
        rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
        try:
            req = RagQuestionRequest(
                messages=messages,
                model=actual_model,  # Use actual_model instead of requested_model
                stream=stream,
                reasoning_level=reasoning_level,
            )
            # prepare_ollama_messages ALWAYS uses RAG - it calls build_rag_context() internally
            ollama_messages, use_model = prepare_ollama_messages(
                req,
                rag_repo,
                embed_provider,
                effective_rerank_client,
                prefix,
                suffix,
                context_chunk_chars,
                context_total_chars,
                confidence_threshold,
                ollama_model,
                reasoning_level=reasoning_level,
            )
            # Ensure use_model is not "rag-ollama" - use config model if needed
            if use_model == "rag-ollama":
                use_model = ollama_model
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
            _log_rag_error("prepare_rag", e)
            return jsonify({"error": str(e)}), 500
        if stream:
            set_proxy_status(STATUS_RESPONSE)
            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                preview = ""
                stream_start_time = time.time()
                full_response = ""
                total_tokens_holder = [0]
                try:
                    for content in chat_client.stream_chat(ollama_messages, use_model):
                        if content:
                            full_response += content
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
                    
                    # Log streaming request
                    stream_latency_ms = int((time.time() - stream_start_time) * 1000)
                    def _approx_tokens(text: str) -> int:
                        if not text:
                            return 0
                        return max(1, int(len(text) / 4))
                    
                    prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
                    prompt_tokens_approx = _approx_tokens(prompt_text)
                    completion_tokens_approx = _approx_tokens(full_response)
                    total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
                    total_tokens_holder[0] = total_tokens_approx
                    
                    try:
                        session_manager = get_session_manager()
                        session = session_manager.get_or_create_session("proxy")
                        logs_repo = get_logs_repository()
                        log_metadata = {
                            "user_query": user_query[:500],
                            "response_preview": full_response[:500],
                            "model": use_model,
                            "latency_ms": stream_latency_ms,
                            "prompt_tokens": prompt_tokens_approx,
                            "completion_tokens": completion_tokens_approx,
                            "total_tokens": total_tokens_approx,
                            "rag_context": rag_context_data,
                            "rag_steps": rag_timings,
                            "stream": True,
                        }
                        logs_repo.add_log(
                            session_id="proxy",
                            level="INFO",
                            message=f"Proxy request (stream): {user_query[:100]}...",
                            source="proxy",
                            metadata=log_metadata,
                        )
                    except Exception as e:
                        _RAG_LOG.warning(f"Failed to log proxy stream request to database: {e}")
                    
                    _RAG_LOG.info(
                        "RAG response (stream) model=%s len=%s preview=%s",
                        use_model,
                        len(full_response),
                        preview[:log_preview] if preview else "",
                    )
                except Exception as e:
                    log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                    _log_rag_error("stream_chat", e)
                    raise
                finally:
                    set_proxy_status(STATUS_IDLE)
                    set_latest_request_seconds(time.time() - start_time)
                    set_latest_request_total_tokens(total_tokens_holder[0] or None)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            set_proxy_status(STATUS_RESPONSE)
            # answer_question ALWAYS uses RAG - it calls build_rag_context() internally
            answer = answer_question(
                req,
                rag_repo,
                embed_provider,
                effective_rerank_client,
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
        finally:
            set_proxy_status(STATUS_IDLE)
            set_latest_request_seconds(time.time() - start_time)
        _prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
        _total_tokens_approx = max(1, int(len(_prompt_text) / 4)) + max(1, int(len(answer.content or "") / 4))
        set_latest_request_total_tokens(_total_tokens_approx)
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
