"""Buffered standard (non-SSE-streaming) chat completion fetch and response assembly."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import Response, jsonify

from infrastructure.metrics import gauge, histogram, increment
from llm_proxy.chat_completions_ollama_proxy import (
    _PLACEHOLDER_REPLY_FALLBACK_EN,
    _append_trace_warning,
    _apply_provider_trace_fields,
    _apply_response_diagnostics,
    _apply_trace_response_text_fields,
    _degenerate_assistant_reply,
    _output_budget_is_exhausted,
    _proxy_ollama_chat_text_parts,
    _text_preview,
    _trace_ollama_api_metrics,
)
from llm_proxy.chat_completions_rag_prep import build_rag_metadata_for_response
from llm_proxy.chat_completions_response_helpers import (
    final_or_compat_content,
    record_reasoning_token_estimates,
    tool_loop_limit_final_message,
)
from llm_proxy.chat_completions_sse_generators import (
    PlainSingleStreamContext,
    iter_plain_single_sse_stream,
)
from llm_proxy.chat_completions_streaming import SSE_MIMETYPE, SSE_RESPONSE_HEADERS
from llm_proxy.chat_completions_upstream_budget import _ollama_message_content_str
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.tool_helpers import (
    _build_tool_arguments,
    _extract_edit_from_response,
    _tool_args_have_substantive_body,
)

_RAG_LOG = logging.getLogger("llm_proxy")

PublishTraceFn = Callable[[dict[str, Any]], None]
PublishArtifactsFn = Callable[..., None]
PersistLogFn = Callable[..., None]
OllamaOptionsOverlayFn = Callable[[], dict[str, Any] | None]
LogRagErrorPrivateFn = Callable[..., None]
RagCompletedPayloadFn = Callable[..., dict[str, Any]]


def record_standard_completion_metrics(
    *,
    private_build: bool,
    use_model: str,
    is_autocomplete: bool,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    rag_ctx: Any | None,
) -> None:
    metric_model = "redacted" if private_build else use_model
    increment("rag_requests_total", tags={"model": metric_model, "is_autocomplete": str(is_autocomplete)})
    histogram("rag_latency_ms", latency_ms, tags={"model": metric_model})
    histogram("rag_prompt_tokens", prompt_tokens, tags={"model": metric_model})
    histogram("rag_completion_tokens", completion_tokens, tags={"model": metric_model})
    if rag_ctx:
        gauge("rag_chunks_count", len(rag_ctx.chunks_info), tags={"model": metric_model})
        gauge("rag_max_score", rag_ctx.max_score, tags={"model": metric_model})
        if rag_ctx.max_score < 0.5:
            increment("rag_low_confidence", tags={"model": metric_model})
    if not rag_ctx or not rag_ctx.chunks_info:
        increment("rag_empty_results", tags={"model": metric_model})


def resolve_legacy_nonstream_tool_calls(
    *,
    content: str,
    tools: list[Any],
    tool_choice_effective: str,
    post_tool_success_turn: bool,
    stream: bool,
    build_sse_streaming: bool,
    selected_edit_tool_name: str | None,
    selected_edit_tool: Any,
    selected_tool_write_capable: bool,
    user_query: str,
) -> tuple[list[dict[str, object]], str]:
    """Extract legacy edit tool_calls from buffered assistant content."""
    tool_calls: list[dict[str, object]] = []
    resolved_content = content
    if (
        tools
        and tool_choice_effective != "none"
        and not post_tool_success_turn
        and (not stream or not build_sse_streaming)
    ):
        edit_payload = _extract_edit_from_response(content or "")
        if edit_payload and selected_edit_tool_name:
            tool_args = _build_tool_arguments(
                selected_tool_name=selected_edit_tool_name,
                selected_tool=selected_edit_tool,
                edit_payload=edit_payload,
                user_query=user_query,
            )
            if selected_tool_write_capable and _tool_args_have_substantive_body(
                selected_edit_tool_name, tool_args
            ):
                tool_calls = [
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": selected_edit_tool_name,
                            "arguments": json.dumps(tool_args, ensure_ascii=False),
                        },
                    }
                ]
            elif not selected_tool_write_capable:
                resolved_content = (
                    f"Cannot apply edit: client tool `{selected_edit_tool_name}` schema does not accept file content. "
                    "Enable a write-capable file edit tool in the IDE (e.g., edit_file/save_file/replace_in_file_range with content/new_text/replacement)."
                )
    return tool_calls, resolved_content


@dataclass(frozen=True)
class StandardNonStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    private_build: bool
    stream: bool
    build_sse_streaming: bool
    client_visible_model: str
    chat_client: Any
    ollama_messages: list[Any]
    use_model: str
    ollama_think: Any
    include_reasoning_content: bool
    include_rag_metadata: bool
    user_query: str
    trace_id: str
    log_preview: int
    start_time: float
    rag_ctx: Any | None
    rag_ctx_for_log: Any | None
    rag_timings: dict[str, float]
    requested_model: str
    is_autocomplete: bool
    tools: list[Any]
    tool_choice_effective: str
    post_tool_success_turn: bool
    selected_edit_tool_name: str | None
    selected_edit_tool: Any
    selected_tool_write_capable: bool
    ollama_options_overlay: OllamaOptionsOverlayFn
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn
    log_rag_error_private: LogRagErrorPrivateFn
    rag_request_completed_payload: RagCompletedPayloadFn


def build_standard_nonstream_response(
    ctx: StandardNonStreamContext,
) -> Response | tuple[Response, int]:
    """Fetch buffered chat, assemble OpenAI response, and return jsonify or single-chunk SSE."""
    content = ""
    content_parts: dict[str, Any] = {}
    budget_exhausted = False
    try:
        ctx.w.set_proxy_status(ctx.w.status_response)
        _apply_provider_trace_fields(
            ctx.trace,
            ctx.chat_client,
            model_id=ctx.use_model,
            operation="chat_api",
        )
        content_parts = _proxy_ollama_chat_text_parts(
            ctx.chat_client,
            ctx.ollama_messages,
            ctx.use_model,
            ctx.ollama_think,
            options_overlay=ctx.ollama_options_overlay(),
        )
        content = final_or_compat_content(
            content_parts,
            include_reasoning_content=ctx.include_reasoning_content,
        )
        if _degenerate_assistant_reply(content) and not str(content_parts.get("reasoning_content") or ""):
            content = _PLACEHOLDER_REPLY_FALLBACK_EN
            content_parts = {
                "visible_content": content,
                "reasoning_content": "",
                "final_content": content,
                "ollama_payload": content_parts.get("ollama_payload") if isinstance(content_parts, dict) else {},
            }
        if (
            str(content_parts.get("reasoning_content") or "")
            and not str(content_parts.get("final_content") or "")
        ):
            tool_loop_limit_message = tool_loop_limit_final_message(ctx.trace)
            if tool_loop_limit_message:
                _append_trace_warning(ctx.trace, "tool_loop_limit_response_guarded")
                content = tool_loop_limit_message
            else:
                _append_trace_warning(ctx.trace, "reasoning_only_response_guarded")
                content = (
                    "[Error: model returned reasoning without final answer. "
                    "Try disabling thinking or shortening the prompt.]"
                )
            content_parts = {
                "visible_content": f"{content_parts.get('visible_content') or ''}\n\n{content}".strip(),
                "reasoning_content": str(content_parts.get("reasoning_content") or ""),
                "final_content": content,
                "ollama_payload": content_parts.get("ollama_payload") if isinstance(content_parts, dict) else {},
            }
        budget_exhausted = _output_budget_is_exhausted(
            ctx.trace,
            content_parts.get("ollama_payload") if isinstance(content_parts, dict) else None,
        )
    except Exception as exc:
        if not ctx.private_build:
            ctx.w.log_webui_error("rag_routes.chat_completions", exc, {"stage": "chat"})
        ctx.log_rag_error_private("chat", exc, private_build=ctx.private_build)
        return jsonify({"error": str(exc)}), 500
    finally:
        ctx.w.set_proxy_status(ctx.w.status_idle)
        ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)

    latency_ms = int((time.time() - ctx.start_time) * 1000)
    prompt_text = " ".join(
        _ollama_message_content_str(m.get("content"))
        for m in ctx.ollama_messages
        if isinstance(m, dict)
    )
    prompt_tokens_approx = max(1, int(len(prompt_text) / 4))
    completion_tokens_approx = max(1, int(len(content or "") / 4))
    total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
    ctx.w.set_latest_request_total_tokens(total_tokens_approx)

    record_standard_completion_metrics(
        private_build=ctx.private_build,
        use_model=ctx.use_model,
        is_autocomplete=ctx.is_autocomplete,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens_approx,
        completion_tokens=completion_tokens_approx,
        rag_ctx=ctx.rag_ctx,
    )

    if not ctx.private_build:
        _RAG_LOG.debug(
            json.dumps(
                ctx.rag_request_completed_payload(
                    user_query=ctx.user_query,
                    trace_id=ctx.trace_id,
                    use_model=ctx.use_model,
                    requested_model=ctx.requested_model,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens_approx,
                    completion_tokens=completion_tokens_approx,
                    rag_context_for_obs=ctx.rag_ctx_for_log,
                    rag_timings=ctx.rag_timings,
                    trace=ctx.trace,
                    stream=bool(ctx.stream),
                    is_autocomplete=bool(ctx.is_autocomplete),
                    native_tools=False,
                )
            )
        )

    content_len = len(content or "")
    content_preview = _text_preview(content or "", ctx.log_preview)
    if not ctx.private_build:
        _RAG_LOG.debug(
            "RAG response model=%s len=%s preview=%s",
            ctx.use_model,
            content_len,
            content_preview,
        )
    ctx.trace["ollama"]["tokens_estimates"] = {
        "prompt_tokens_estimated": prompt_tokens_approx,
        "completion_tokens_estimated": completion_tokens_approx,
        "total_tokens_estimated": total_tokens_approx,
    }
    ctx.trace["response"] = {
        "latency_ms": latency_ms,
        **_trace_ollama_api_metrics(
            content_parts.get("ollama_payload") if isinstance(content_parts, dict) else None,
            model_id=ctx.use_model,
        ),
    }
    record_reasoning_token_estimates(
        ctx.trace["response"],
        content_parts["reasoning_content"],
        content_parts["final_content"],
    )
    _apply_trace_response_text_fields(
        ctx.trace["response"],
        visible_content=content_parts["visible_content"],
        reasoning_content=content_parts["reasoning_content"],
        final_content=content_parts["final_content"],
        log_preview=ctx.log_preview,
    )
    _apply_response_diagnostics(ctx.trace)
    ctx.trace["steps"].append(
        {
            "name": "ollama_chat",
            "duration_ms": int(latency_ms),
            "tokens_in_est": prompt_tokens_approx,
            "tokens_out_est": completion_tokens_approx,
        }
    )
    ctx.publish_response_artifacts(
        visible_content=content_parts["visible_content"],
        reasoning_content=content_parts["reasoning_content"],
        final_content=content_parts["final_content"],
    )
    ctx.publish_trace(ctx.trace)

    tool_calls, content = resolve_legacy_nonstream_tool_calls(
        content=content,
        tools=ctx.tools,
        tool_choice_effective=ctx.tool_choice_effective,
        post_tool_success_turn=ctx.post_tool_success_turn,
        stream=ctx.stream,
        build_sse_streaming=ctx.build_sse_streaming,
        selected_edit_tool_name=ctx.selected_edit_tool_name,
        selected_edit_tool=ctx.selected_edit_tool,
        selected_tool_write_capable=ctx.selected_tool_write_capable,
        user_query=ctx.user_query,
    )

    ctx.trace["response"]["tool_calls_count"] = len(tool_calls)
    if tool_calls:
        ctx.trace["response"]["tool_calls"] = tool_calls
        ctx.publish_trace(ctx.trace)

    msg_obj: dict[str, object] = {
        "role": "assistant",
        "content": None if tool_calls else content,
    }
    if content_parts["reasoning_content"]:
        msg_obj["reasoning_content"] = content_parts["reasoning_content"]
    if tool_calls:
        msg_obj["tool_calls"] = tool_calls
    choice = {
        "index": 0,
        "message": msg_obj,
        "finish_reason": "tool_calls" if tool_calls else ("length" if budget_exhausted else "stop"),
    }
    response_data = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": 0,
        "model": ctx.client_visible_model,
        "choices": [choice],
    }

    if ctx.include_rag_metadata and ctx.rag_ctx:
        response_data["rag_metadata"] = build_rag_metadata_for_response(ctx.rag_ctx)

    if ctx.stream:
        ctx.trace["request"]["sse_single_chunk"] = True
        ctx.trace["ollama"]["chat_stream"] = False
        ctx.publish_trace(ctx.trace)

        finish_sse = str(choice.get("finish_reason") or ("tool_calls" if tool_calls else "stop"))
        response_id = str(response_data.get("id") or f"chatcmpl-{uuid.uuid4().hex[:24]}")

        return Response(
            iter_plain_single_sse_stream(
                PlainSingleStreamContext(
                    response_id=response_id,
                    client_visible_model=ctx.client_visible_model,
                    content=str(content or ""),
                    content_parts=content_parts,
                    tool_calls=tool_calls,
                    finish_reason=finish_sse,
                    include_reasoning_content=ctx.include_reasoning_content,
                    private_build=ctx.private_build,
                    user_query=ctx.user_query,
                    content_preview=content_preview,
                    latency_ms=latency_ms,
                    trace=ctx.trace,
                    prompt_tokens_approx=prompt_tokens_approx,
                    completion_tokens_approx=completion_tokens_approx,
                    total_tokens_approx=total_tokens_approx,
                    persist_proxy_request_log=ctx.persist_proxy_request_log,
                )
            ),
            mimetype=SSE_MIMETYPE,
            headers=SSE_RESPONSE_HEADERS,
        )

    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request: {ctx.user_query[:100]}...",
            response_preview=content_preview,
            latency_ms_value=latency_ms,
            trace_payload=ctx.trace,
            stream_value=False,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=prompt_tokens_approx,
            completion_tokens_value=completion_tokens_approx,
            total_tokens_value=total_tokens_approx,
            warn_label="non-stream",
        )

    return jsonify(response_data)
