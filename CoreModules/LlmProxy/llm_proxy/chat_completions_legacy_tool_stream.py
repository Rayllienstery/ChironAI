"""Buffered chat + edit resolution for legacy tool-mode SSE streaming."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import Response

from llm_proxy.chat_completions_ollama_proxy import (
    _apply_response_diagnostics,
    _apply_trace_response_text_fields,
)
from llm_proxy.chat_completions_sse_generators import (
    LegacyPlainTextStreamContext,
    LegacyToolCallStreamContext,
    iter_legacy_plain_text_sse_stream,
    iter_legacy_tool_call_sse_stream,
)
from llm_proxy.chat_completions_streaming import (
    SSE_MIMETYPE,
    SSE_RESPONSE_HEADERS,
    approx_token_count,
)
from llm_proxy.chat_completions_streaming_orchestration import (
    estimate_prompt_tokens_from_ollama_messages,
)
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
OllamaOptionsOverlayFn = Callable[[], dict[str, Any]]
LogRagErrorPrivateFn = Callable[..., None]
RagCompletedPayloadFn = Callable[..., dict[str, Any]]


def is_legacy_tool_stream_mode(
    *,
    stream: bool,
    tools: Any,
    tool_choice_effective: str,
    post_tool_success_turn: bool,
) -> bool:
    return bool(stream and tools and tool_choice_effective != "none" and not post_tool_success_turn)


def compact_messages_for_chat_retry(ollama_messages: list[Any]) -> list[dict[str, object]]:
    compact_messages: list[dict[str, object]] = []
    if not ollama_messages:
        return compact_messages
    first_system = next(
        (m for m in ollama_messages if isinstance(m, dict) and m.get("role") == "system"),
        None,
    )
    last_user_msg = next(
        (m for m in reversed(ollama_messages) if isinstance(m, dict) and m.get("role") == "user"),
        None,
    )
    if isinstance(first_system, dict):
        compact_messages.append(first_system)
    if isinstance(last_user_msg, dict):
        compact_messages.append(last_user_msg)
    return compact_messages


@dataclass(frozen=True)
class LegacyToolStreamEditResolution:
    edit_payload: dict[str, object] | None
    tool_plain_fallback: str
    tool_call: dict[str, Any] | None


def resolve_legacy_tool_stream_edit(
    *,
    streamed_content: str,
    stream_tool_error: str | None,
    selected_edit_tool_name: str | None,
    selected_edit_tool: Any,
    selected_tool_write_capable: bool,
    user_query: str,
) -> LegacyToolStreamEditResolution:
    edit_payload = _extract_edit_from_response(streamed_content or "")
    tool_plain_fallback = (streamed_content or "").strip()
    tool_call: dict[str, Any] | None = None

    if (not stream_tool_error) and edit_payload and selected_edit_tool_name:
        tool_args = _build_tool_arguments(
            selected_tool_name=selected_edit_tool_name,
            selected_tool=selected_edit_tool,
            edit_payload=edit_payload,
            user_query=user_query,
        )
        if not selected_tool_write_capable:
            tool_plain_fallback = (
                f"Cannot apply edit: client tool `{selected_edit_tool_name}` schema does not accept file content. "
                "Enable a write-capable file edit tool in the IDE (e.g., edit_file/save_file/replace_in_file_range with content/new_text/replacement)."
            )
            edit_payload = None
        elif not _tool_args_have_substantive_body(selected_edit_tool_name, tool_args):
            tool_plain_fallback = (
                "Cannot apply edit: model did not provide a non-empty edit body (content/new_text/replacement). "
                "Please retry."
            )
            edit_payload = None
        else:
            tool_call = {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": selected_edit_tool_name,
                    "arguments": json.dumps(tool_args, ensure_ascii=False),
                },
            }

    if (not stream_tool_error) and (not edit_payload) and (not tool_plain_fallback):
        tool_plain_fallback = (
            "Model returned an empty response; no tool call was emitted. Please retry."
        )

    return LegacyToolStreamEditResolution(
        edit_payload=edit_payload,
        tool_plain_fallback=tool_plain_fallback,
        tool_call=tool_call,
    )


@dataclass(frozen=True)
class LegacyToolStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    trace_id: str
    private_build: bool
    client_visible_model: str
    chat_client: Any
    ollama_messages: list[Any]
    use_model: str
    ollama_think: Any
    user_query: str
    log_preview: int
    start_time: float
    rag_ctx_for_log: Any
    rag_timings: Any
    requested_model: str
    is_autocomplete: bool
    selected_edit_tool_name: str | None
    selected_edit_tool: Any
    selected_tool_write_capable: bool
    ollama_options_overlay: OllamaOptionsOverlayFn
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn
    log_rag_error_private: LogRagErrorPrivateFn
    rag_request_completed_payload: RagCompletedPayloadFn


def _fetch_buffered_chat_content(ctx: LegacyToolStreamContext) -> tuple[str, str | None, float]:
    stream_start_time = time.time()
    stream_tool_error: str | None = None
    ctx.w.set_proxy_status(ctx.w.status_response)
    try:
        streamed_content = ctx.chat_client.chat(
            ctx.ollama_messages,
            ctx.use_model,
            stream=False,
            options=ctx.ollama_options_overlay(),
            think=ctx.ollama_think,
        )
    except Exception:
        compact_messages = compact_messages_for_chat_retry(ctx.ollama_messages)
        try:
            streamed_content = ctx.chat_client.chat(
                compact_messages or ctx.ollama_messages,
                ctx.use_model,
                stream=False,
                options=ctx.ollama_options_overlay(),
                think=ctx.ollama_think,
            )
        except Exception as e2:
            if not ctx.private_build:
                ctx.w.log_webui_error(
                    "rag_routes.chat_completions",
                    e2,
                    {"stage": "chat_stream_tool_mode"},
                )
            ctx.log_rag_error_private("chat_stream_tool_mode", e2, private_build=ctx.private_build)
            stream_tool_error = str(e2)
            streamed_content = ""
    finally:
        ctx.w.set_proxy_status(ctx.w.status_idle)
        ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)

    return streamed_content or "", stream_tool_error, stream_start_time


def _persist_legacy_tool_stream_log(
    ctx: LegacyToolStreamContext,
    *,
    stream_start_time: float,
    response_preview: str,
    prompt_tokens: int,
    completion_tokens: int,
    stream_tool_mode: str,
    warn_label: str,
    message_prefix: str,
) -> None:
    latency_ms = int((time.time() - stream_start_time) * 1000)
    if ctx.private_build:
        return
    ctx.persist_proxy_request_log(
        message=f"{message_prefix}: {ctx.user_query[:100]}...",
        response_preview=response_preview,
        latency_ms_value=latency_ms,
        trace_payload=ctx.trace,
        stream_value=True,
        include_rag_fields=True,
        include_token_fields=True,
        prompt_tokens_value=prompt_tokens,
        completion_tokens_value=completion_tokens,
        total_tokens_value=prompt_tokens + completion_tokens,
        extra_metadata={"stream_tool_mode": stream_tool_mode},
        warn_label=warn_label,
    )
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
                stream=True,
                is_autocomplete=bool(ctx.is_autocomplete),
                native_tools=False,
            )
            | {"stream_tool_mode": stream_tool_mode}
        )
    )


def try_build_legacy_tool_stream_response(ctx: LegacyToolStreamContext) -> Response | None:
    """Run buffered legacy tool-mode chat; return SSE Response or None to fall through."""
    streamed_content, stream_tool_error, stream_start_time = _fetch_buffered_chat_content(ctx)

    if stream_tool_error:
        ctx.trace["response"]["tool_mode_error"] = stream_tool_error[:500]
        ctx.publish_trace(ctx.trace)

    resolution = resolve_legacy_tool_stream_edit(
        streamed_content=streamed_content,
        stream_tool_error=stream_tool_error,
        selected_edit_tool_name=ctx.selected_edit_tool_name,
        selected_edit_tool=ctx.selected_edit_tool,
        selected_tool_write_capable=ctx.selected_tool_write_capable,
        user_query=ctx.user_query,
    )

    if (not stream_tool_error) and resolution.tool_call and ctx.selected_edit_tool_name:
        tool_call = resolution.tool_call
        ctx.trace["response"] = {
            "content_preview": "",
            "content_length_chars": 0,
            "latency_ms": int((time.time() - stream_start_time) * 1000),
            "tool_calls_count": 1,
            "tool_calls": [tool_call],
        }
        ctx.publish_trace(ctx.trace)
        _persist_legacy_tool_stream_log(
            ctx,
            stream_start_time=stream_start_time,
            response_preview="",
            prompt_tokens=0,
            completion_tokens=0,
            stream_tool_mode="tool_calls",
            warn_label="stream_tool_mode (tool_calls)",
            message_prefix="Proxy request (stream tool)",
        )
        return Response(
            iter_legacy_tool_call_sse_stream(
                LegacyToolCallStreamContext(
                    client_visible_model=ctx.client_visible_model,
                    tool_call=tool_call,
                    selected_edit_tool_name=ctx.selected_edit_tool_name,
                )
            ),
            mimetype=SSE_MIMETYPE,
            headers=SSE_RESPONSE_HEADERS,
        )

    if (not stream_tool_error) and resolution.tool_plain_fallback:
        tool_plain_fallback = resolution.tool_plain_fallback
        ctx.trace["response"] = {
            "latency_ms": int((time.time() - stream_start_time) * 1000),
            "tool_calls_count": 0,
        }
        _apply_trace_response_text_fields(
            ctx.trace["response"],
            visible_content=tool_plain_fallback,
            reasoning_content="",
            final_content=tool_plain_fallback,
            log_preview=ctx.log_preview,
        )
        _apply_response_diagnostics(ctx.trace)
        ctx.publish_response_artifacts(
            visible_content=tool_plain_fallback,
            reasoning_content="",
            final_content=tool_plain_fallback,
        )
        ctx.publish_trace(ctx.trace)

        prompt_tokens = estimate_prompt_tokens_from_ollama_messages(ctx.ollama_messages)
        completion_tokens = approx_token_count(tool_plain_fallback)
        _persist_legacy_tool_stream_log(
            ctx,
            stream_start_time=stream_start_time,
            response_preview=tool_plain_fallback,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            stream_tool_mode="plain_text_fallback",
            warn_label="stream_tool_mode (plain)",
            message_prefix="Proxy request (stream tool plain)",
        )
        return Response(
            iter_legacy_plain_text_sse_stream(
                LegacyPlainTextStreamContext(
                    client_visible_model=ctx.client_visible_model,
                    tool_plain_fallback=tool_plain_fallback,
                )
            ),
            mimetype=SSE_MIMETYPE,
            headers=SSE_RESPONSE_HEADERS,
        )

    return None
