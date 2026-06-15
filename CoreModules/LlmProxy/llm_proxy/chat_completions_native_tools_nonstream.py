"""Buffered (non-streaming) native-tools chat with retry cascade and response assembly."""

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
from llm_proxy.chat_completions_gemini_native import (
    _persist_gemini_tool_calls_state,
    _sanitize_outgoing_shell_tool_calls,
)
from llm_proxy.chat_completions_ollama_proxy import (
    _append_trace_warning,
    _apply_provider_trace_fields,
    _apply_response_diagnostics,
    _apply_trace_response_text_fields,
    _output_budget_exhaustion_error,
    _trace_ollama_api_metrics,
)
from llm_proxy.chat_completions_rag_prep import build_rag_metadata_for_response
from llm_proxy.chat_completions_response_helpers import (
    final_or_compat_content,
    record_reasoning_token_estimates,
    text_parts_from_openai_assistant_message,
)
from llm_proxy.chat_completions_sse_generators import (
    NativeToolsSingleStreamContext,
    iter_native_tools_single_sse_stream,
)
from llm_proxy.chat_completions_streaming import SSE_MIMETYPE, SSE_RESPONSE_HEADERS
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.ollama_compat import (
    chat_error_suggests_no_think,
    chat_error_suggests_no_tools,
    ollama_chat_tool_choice_payload_value,
    ollama_message_to_openai_assistant,
    openai_finish_reason_from_ollama,
)

_RAG_LOG = logging.getLogger("llm_proxy")

PublishTraceFn = Callable[[dict[str, Any]], None]
PublishArtifactsFn = Callable[..., None]
PersistLogFn = Callable[..., None]
OllamaOptionsOverlayFn = Callable[[], dict[str, Any] | None]
LogRagErrorPrivateFn = Callable[..., None]
RagCompletedPayloadFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class NativeToolsBufferedChatResult:
    data: dict[str, object]
    error: str | None


def build_native_tools_ollama_body(
    *,
    chat_client: Any,
    use_model: str,
    native_ollama_messages_for_upstream: list[Any],
    ollama_think: Any,
    oll_tools: list[Any] | None,
    tool_choice_effective: Any,
    ollama_options_overlay: OllamaOptionsOverlayFn,
) -> dict[str, object]:
    default_options = dict(getattr(chat_client, "_default_options", None) or {})
    options_overlay = ollama_options_overlay()
    if options_overlay:
        default_options.update(options_overlay)
    body: dict[str, object] = {
        "model": use_model,
        "messages": native_ollama_messages_for_upstream,
        "stream": False,
        "options": dict(default_options),
    }
    if ollama_think is not None:
        body["think"] = ollama_think
    if oll_tools:
        body["tools"] = oll_tools
    tool_choice_payload = ollama_chat_tool_choice_payload_value(tool_choice_effective)
    if tool_choice_payload is not None:
        body["tool_choice"] = tool_choice_payload
    return body


def call_native_tools_buffered_chat_with_retries(
    *,
    chat_client: Any,
    trace: dict[str, Any],
    body_ollama: dict[str, object],
    native_ollama_messages: list[Any],
    use_model: str,
    ollama_think: Any,
    ollama_options_overlay: OllamaOptionsOverlayFn,
) -> NativeToolsBufferedChatResult:
    """Call chat_api with tools/think retry cascade, or fall back to chat()."""
    chat_fn = getattr(chat_client, "chat_api", None)
    if callable(chat_fn):
        attempt: dict[str, object] = dict(body_ollama)
        last_exc: Exception | None = None
        data: dict[str, object] = {}
        for _ in range(3):
            try:
                data = chat_fn(attempt)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if chat_error_suggests_no_tools(exc) and "tools" in attempt:
                    attempt.pop("tools", None)
                    attempt.pop("tool_choice", None)
                    trace["request"]["native_tools_fallback"] = "stripped_tools_unsupported"
                    continue
                if chat_error_suggests_no_think(exc) and "think" in attempt:
                    attempt.pop("think", None)
                    trace["request"]["native_think_fallback"] = "stripped_unsupported"
                    continue
                break
        if last_exc is not None:
            raise last_exc
        return NativeToolsBufferedChatResult(data=data, error=None)

    msg_only = chat_client.chat(
        native_ollama_messages,
        use_model,
        stream=False,
        options=ollama_options_overlay(),
        think=ollama_think,
    )
    return NativeToolsBufferedChatResult(
        data={"message": {"role": "assistant", "content": msg_only}},
        error=None,
    )


def record_native_tools_completion_metrics(
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


@dataclass(frozen=True)
class NativeToolsNonStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    private_build: bool
    stream: bool
    client_visible_model: str
    chat_client: Any
    native_ollama_messages: list[Any]
    native_ollama_messages_for_upstream: list[Any]
    use_model: str
    ollama_think: Any
    oll_tools: list[Any] | None
    tool_choice_effective: Any
    include_reasoning_content: bool
    include_rag_metadata: bool
    user_query: str
    trace_id: str
    proxy_db_path: str | None
    log_preview: int
    start_time: float
    rag_ctx: Any | None
    rag_ctx_for_log: Any | None
    rag_timings: dict[str, float]
    requested_model: str
    is_autocomplete: bool
    post_tool_success_turn: bool
    native_tools_diag: dict[str, Any]
    ollama_options_overlay: OllamaOptionsOverlayFn
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn
    log_rag_error_private: LogRagErrorPrivateFn
    rag_request_completed_payload: RagCompletedPayloadFn


def try_build_native_tools_nonstream_response(
    ctx: NativeToolsNonStreamContext,
) -> Response | tuple[Response, int] | None:
    """Run buffered native-tools chat and return HTTP response, or None if upstream failed early."""
    body_ollama = build_native_tools_ollama_body(
        chat_client=ctx.chat_client,
        use_model=ctx.use_model,
        native_ollama_messages_for_upstream=ctx.native_ollama_messages_for_upstream,
        ollama_think=ctx.ollama_think,
        oll_tools=ctx.oll_tools,
        tool_choice_effective=ctx.tool_choice_effective,
        ollama_options_overlay=ctx.ollama_options_overlay,
    )

    ctx.w.set_proxy_status(ctx.w.status_response)
    native_err: str | None = None
    data: dict[str, object] = {}
    try:
        _apply_provider_trace_fields(
            ctx.trace,
            ctx.chat_client,
            model_id=ctx.use_model,
            operation="chat_api",
        )
        chat_result = call_native_tools_buffered_chat_with_retries(
            chat_client=ctx.chat_client,
            trace=ctx.trace,
            body_ollama=body_ollama,
            native_ollama_messages=ctx.native_ollama_messages,
            use_model=ctx.use_model,
            ollama_think=ctx.ollama_think,
            ollama_options_overlay=ctx.ollama_options_overlay,
        )
        data = chat_result.data
    except Exception as exc:
        if not ctx.private_build:
            meta: dict[str, Any] = {"stage": "native_tools_ollama"}
            if ctx.native_tools_diag:
                meta["native_tools_diag"] = ctx.native_tools_diag
            ctx.w.log_webui_error("rag_routes.chat_completions", exc, meta)
        ctx.log_rag_error_private("native_tools_ollama", exc, private_build=ctx.private_build)
        native_err = str(exc)
    finally:
        ctx.w.set_proxy_status(ctx.w.status_idle)
        ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)

    if native_err:
        return jsonify({"error": native_err}), 500

    err_obj = data.get("error")
    if err_obj:
        return jsonify({"error": str(err_obj)}), 502

    if not data:
        return jsonify(
            {"error": "Empty response from Ollama (stream or connection closed without data)"}
        ), 502

    oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
    if not oll_msg and not err_obj:
        return jsonify(
            {
                "error": "Ollama returned no assistant message",
                "detail": json.dumps(data, ensure_ascii=False)[:800],
            }
        ), 502

    openai_msg = ollama_message_to_openai_assistant(oll_msg)
    finish = openai_finish_reason_from_ollama(
        oll_msg,
        ollama_done_reason=data.get("done_reason"),
    )
    tool_calls_out = openai_msg.get("tool_calls") if isinstance(openai_msg.get("tool_calls"), list) else []
    tool_calls_recovered_from_text = bool(
        tool_calls_out
        and not (
            isinstance(oll_msg.get("tool_calls"), list)
            and bool(oll_msg.get("tool_calls"))
        )
    )
    tool_calls_out, shell_sanitize_count = _sanitize_outgoing_shell_tool_calls(tool_calls_out)
    if tool_calls_recovered_from_text:
        _append_trace_warning(ctx.trace, "native_tool_calls_recovered_from_text")
        finish = "tool_calls"
    gemini_tool_state_upserted = _persist_gemini_tool_calls_state(
        tool_calls=tool_calls_out,
        model_name=ctx.use_model,
        trace_id=ctx.trace_id,
        db_path=ctx.proxy_db_path,
    )
    content_parts = text_parts_from_openai_assistant_message(openai_msg)
    content_str = final_or_compat_content(
        content_parts,
        include_reasoning_content=ctx.include_reasoning_content,
    )
    if (
        content_parts["reasoning_content"]
        and not content_parts["final_content"]
        and not tool_calls_out
    ):
        _append_trace_warning(ctx.trace, "reasoning_only_response_guarded")
        content_str = (
            "[Error: model returned reasoning without final answer. "
            "Try disabling thinking or shortening the prompt.]"
        )
        content_parts = {
            "visible_content": f"{content_parts['visible_content']}\n\n{content_str}".strip(),
            "reasoning_content": content_parts["reasoning_content"],
            "final_content": content_str,
        }
    budget_error = _output_budget_exhaustion_error(ctx.trace, data if isinstance(data, dict) else None)
    if budget_error and not tool_calls_out:
        content_str = f"{content_str}\n\n{budget_error}".strip() if content_str.strip() else budget_error
        content_parts = {
            "visible_content": content_str,
            "reasoning_content": content_parts["reasoning_content"],
            "final_content": f"{content_parts['final_content']}\n\n{budget_error}".strip(),
        }
        finish = "length"

    latency_ms = int((time.time() - ctx.start_time) * 1000)
    prompt_tokens = max(
        1,
        int(len(json.dumps(ctx.native_ollama_messages_for_upstream, ensure_ascii=False)) / 4),
    )
    completion_tokens = max(1, int(len(content_str or "") / 4))
    ctx.w.set_latest_request_total_tokens(prompt_tokens + completion_tokens)

    record_native_tools_completion_metrics(
        private_build=ctx.private_build,
        use_model=ctx.use_model,
        is_autocomplete=ctx.is_autocomplete,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
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
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    rag_context_for_obs=ctx.rag_ctx_for_log,
                    rag_timings=ctx.rag_timings,
                    trace=ctx.trace,
                    stream=bool(ctx.stream),
                    is_autocomplete=bool(ctx.is_autocomplete),
                    native_tools=True,
                )
            )
        )

    ctx.trace["response"] = {
        "latency_ms": latency_ms,
        "tool_calls_count": len(tool_calls_out),
        "native_tools": True,
        **_trace_ollama_api_metrics(data if isinstance(data, dict) else None, model_id=ctx.use_model),
    }
    record_reasoning_token_estimates(
        ctx.trace["response"],
        content_parts["reasoning_content"],
        content_parts["final_content"],
    )
    _apply_trace_response_text_fields(
        ctx.trace["response"],
        visible_content=content_parts["visible_content"] or content_str,
        reasoning_content=content_parts["reasoning_content"],
        final_content=content_parts["final_content"],
        log_preview=ctx.log_preview,
    )
    _apply_response_diagnostics(ctx.trace)
    if tool_calls_out:
        ctx.trace["response"]["tool_calls"] = tool_calls_out
        if ctx.post_tool_success_turn:
            ctx.trace["response"]["post_tool_returned_tool_calls"] = True
    if tool_calls_recovered_from_text:
        ctx.trace["response"]["tool_calls_recovered_from_text"] = True
    if gemini_tool_state_upserted:
        ctx.trace["response"]["gemini_tool_state_upserted_count"] = int(gemini_tool_state_upserted)
    if shell_sanitize_count:
        ctx.trace["response"]["shell_tool_sanitized_count"] = int(shell_sanitize_count)

    choice_msg: dict[str, object] = {
        "role": "assistant",
        "content": None if tool_calls_out else (content_str or None),
    }
    if content_parts["reasoning_content"]:
        choice_msg["reasoning_content"] = content_parts["reasoning_content"]
    if tool_calls_out:
        choice_msg["tool_calls"] = tool_calls_out
    response_data: dict[str, object] = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": 0,
        "model": ctx.client_visible_model,
        "choices": [
            {
                "index": 0,
                "message": choice_msg,
                "finish_reason": finish,
            }
        ],
    }
    if ctx.include_rag_metadata and ctx.rag_ctx:
        response_data["rag_metadata"] = build_rag_metadata_for_response(ctx.rag_ctx)

    if not ctx.stream:
        ctx.trace["steps"].append(
            {
                "name": "provider_chat_native_tools",
                "duration_ms": int(latency_ms),
                "tokens_in_est": prompt_tokens,
                "tokens_out_est": completion_tokens,
            }
        )
        ctx.publish_response_artifacts(
            visible_content=content_parts["visible_content"] or content_str,
            reasoning_content=content_parts["reasoning_content"],
            final_content=content_parts["final_content"],
        )
        ctx.publish_trace(ctx.trace)
        if not ctx.private_build:
            ctx.persist_proxy_request_log(
                message=f"Proxy request (native tools): {ctx.user_query[:100]}...",
                response_preview=(content_str or ""),
                latency_ms_value=latency_ms,
                trace_payload=ctx.trace,
                stream_value=False,
                include_rag_fields=False,
                include_token_fields=False,
                warn_label="native-tools",
            )
        return jsonify(response_data)

    ctx.trace["request"]["sse_single_chunk"] = True

    return Response(
        iter_native_tools_single_sse_stream(
            NativeToolsSingleStreamContext(
                w=ctx.w,
                trace=ctx.trace,
                private_build=ctx.private_build,
                client_visible_model=ctx.client_visible_model,
                content_str=content_str,
                content_parts=content_parts,
                tool_calls_out=tool_calls_out,
                finish=finish,
                include_reasoning_content=ctx.include_reasoning_content,
                user_query=ctx.user_query,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                start_time=ctx.start_time,
                publish_trace=ctx.publish_trace,
                publish_response_artifacts=ctx.publish_response_artifacts,
                persist_proxy_request_log=ctx.persist_proxy_request_log,
            )
        ),
        mimetype=SSE_MIMETYPE,
        headers=SSE_RESPONSE_HEADERS,
    )
