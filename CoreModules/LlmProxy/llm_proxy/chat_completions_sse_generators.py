"""SSE generator factories for chat completion streaming paths."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from llm_proxy.chat_completions_gemini_native import (
    _persist_gemini_tool_calls_state,
    _sse_tool_calls_payload,
)
from llm_proxy.chat_completions_ollama_proxy import (
    _append_trace_warning,
    _apply_provider_trace_fields,
    _apply_response_diagnostics,
    _apply_trace_response_text_fields,
    _iter_proxy_ollama_chat_stream,
    _output_budget_exhaustion_error,
    _trace_ollama_api_metrics,
)
from llm_proxy.chat_completions_response_helpers import (
    record_reasoning_token_estimates,
    upstream_chat_error_message,
)
from llm_proxy.chat_completions_streaming import (
    StreamContentAccumulator,
    append_budget_error_chunks,
    approx_token_count,
    iter_sse_finish_with_done,
    iter_sse_from_ollama_stream_events,
    iter_sse_plain_content_response,
    iter_sse_single_shot_assistant,
    iter_sse_tool_calls_response,
    iter_sse_tool_limit_response,
    reasoning_guard_limit_from_env,
    sse_content_chunk,
    sse_role_assistant_chunk,
    stream_completion_id,
)
from llm_proxy.chat_completions_streaming_orchestration import (
    apply_standard_stream_budget_to_content,
    apply_stream_empty_response_fallback,
    build_native_tools_stream_response_base,
    build_ollama_stream_token_estimates_dict,
    build_provider_stream_step,
    build_standard_stream_response_base,
    build_stream_trace_token_estimates,
    estimate_prompt_tokens_from_messages_json,
    estimate_prompt_tokens_from_ollama_messages,
    native_tools_stream_trace_response_extras,
    resolve_native_stream_tool_calls,
    resolve_stream_finish_reason,
)
from llm_proxy.contracts import LlmProxyWiring

_RAG_LOG = logging.getLogger("llm_proxy")

PublishTraceFn = Callable[[dict[str, Any]], None]
PublishArtifactsFn = Callable[..., None]
PersistLogFn = Callable[..., None]
OllamaOptionsOverlayFn = Callable[[], dict[str, Any]]
LogRagErrorPrivateFn = Callable[..., None]
RagCompletedPayloadFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolLimitStreamContext:
    response_id: str
    client_visible_model: str
    content: str
    private_build: bool
    user_query: str
    log_preview: int
    latency_ms: int
    trace: dict[str, Any]
    prompt_tokens_approx: int
    completion_tokens_approx: int
    total_tokens_approx: int
    persist_proxy_request_log: PersistLogFn


@dataclass(frozen=True)
class NativeToolsStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    private_build: bool
    client_visible_model: str
    chat_client: Any
    native_ollama_messages_for_upstream: list[Any]
    use_model: str
    ollama_think: Any
    oll_tools: Any
    tool_choice_effective: Any
    include_reasoning_content: bool
    user_query: str
    trace_id: str
    proxy_db_path: str | None
    log_preview: int
    start_time: float
    rag_ctx_for_log: Any
    rag_timings: Any
    requested_model: str
    is_autocomplete: bool
    ollama_options_overlay: OllamaOptionsOverlayFn
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn
    log_rag_error_private: LogRagErrorPrivateFn
    rag_request_completed_payload: RagCompletedPayloadFn


@dataclass(frozen=True)
class NativeToolsSingleStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    private_build: bool
    client_visible_model: str
    content_str: str
    content_parts: dict[str, Any]
    tool_calls_out: list[Any]
    finish: str
    include_reasoning_content: bool
    user_query: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    start_time: float
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn


@dataclass(frozen=True)
class LegacyToolCallStreamContext:
    client_visible_model: str
    tool_call: dict[str, Any]
    selected_edit_tool_name: str


@dataclass(frozen=True)
class LegacyPlainTextStreamContext:
    client_visible_model: str
    tool_plain_fallback: str


@dataclass(frozen=True)
class StandardStreamContext:
    w: LlmProxyWiring
    trace: dict[str, Any]
    trace_id: str
    private_build: bool
    client_visible_model: str
    chat_client: Any
    ollama_messages: list[Any]
    use_model: str
    ollama_think: Any
    include_reasoning_content: bool
    user_query: str
    log_preview: int
    start_time: float
    rag_ctx_for_log: Any
    rag_timings: Any
    requested_model: str
    is_autocomplete: bool
    ollama_options_overlay: OllamaOptionsOverlayFn
    publish_trace: PublishTraceFn
    publish_response_artifacts: PublishArtifactsFn
    persist_proxy_request_log: PersistLogFn
    log_rag_error_private: LogRagErrorPrivateFn
    rag_request_completed_payload: RagCompletedPayloadFn


@dataclass(frozen=True)
class PlainSingleStreamContext:
    response_id: str
    client_visible_model: str
    content: str
    content_parts: dict[str, Any]
    tool_calls: list[Any]
    finish_reason: str
    include_reasoning_content: bool
    private_build: bool
    user_query: str
    content_preview: str
    latency_ms: int
    trace: dict[str, Any]
    prompt_tokens_approx: int
    completion_tokens_approx: int
    total_tokens_approx: int
    persist_proxy_request_log: PersistLogFn


def iter_tool_limit_sse_stream(ctx: ToolLimitStreamContext) -> Iterator[str]:
    yield from iter_sse_tool_limit_response(ctx.response_id, ctx.client_visible_model, ctx.content)
    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request (tool limit): {ctx.user_query[:100]}...",
            response_preview=ctx.content[: ctx.log_preview],
            latency_ms_value=ctx.latency_ms,
            trace_payload=ctx.trace,
            stream_value=True,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=ctx.prompt_tokens_approx,
            completion_tokens_value=ctx.completion_tokens_approx,
            total_tokens_value=ctx.total_tokens_approx,
            ollama_chat_stream=False,
            sse_single_chunk=True,
            extra_metadata={"tool_loop_limit_response": True},
            warn_label="tool limit",
        )


def iter_native_tools_sse_stream(ctx: NativeToolsStreamContext) -> Iterator[str]:
    oid = stream_completion_id()
    stream_start_time = time.time()
    stream_acc = StreamContentAccumulator()
    reasoning_guard_limit_chars = reasoning_guard_limit_from_env()
    total_tokens_holder = [0]

    yield sse_role_assistant_chunk(oid, ctx.client_visible_model)

    def _on_reasoning_guard() -> None:
        _append_trace_warning(ctx.trace, "reasoning_only_guard_triggered")
        ctx.trace["request"]["reasoning_only_guard_chars"] = reasoning_guard_limit_chars

    try:
        _apply_provider_trace_fields(
            ctx.trace,
            ctx.chat_client,
            model_id=ctx.use_model,
            operation="chat_api_stream_events",
        )
        yield from iter_sse_from_ollama_stream_events(
            _iter_proxy_ollama_chat_stream(
                ctx.chat_client,
                ctx.native_ollama_messages_for_upstream,
                ctx.use_model,
                ctx.ollama_think,
                options_overlay=ctx.ollama_options_overlay(),
                tools=ctx.oll_tools,
                tool_choice=ctx.tool_choice_effective,
            ),
            completion_id=oid,
            client_visible_model=ctx.client_visible_model,
            include_reasoning_content=ctx.include_reasoning_content,
            accumulator=stream_acc,
            reasoning_guard_limit_chars=reasoning_guard_limit_chars,
            on_reasoning_guard=_on_reasoning_guard,
        )
    except Exception as exc:
        if not ctx.private_build:
            ctx.w.log_webui_error("rag_routes.chat_completions", exc, {"stage": "native_tools_stream"})
        ctx.log_rag_error_private("native_tools_stream", exc, private_build=ctx.private_build)
        err_text = upstream_chat_error_message(exc, ctx.trace, model=ctx.use_model)
        stream_acc.visible_parts.append(err_text)
        stream_acc.final_parts.append(err_text)
        yield sse_content_chunk(oid, ctx.client_visible_model, err_text)

    full_content = stream_acc.visible_content
    reasoning_content = stream_acc.reasoning_content
    final_content = stream_acc.final_content
    tool_calls_raw = stream_acc.tool_calls_raw
    ollama_done_payload = stream_acc.ollama_done_payload
    ollama_done_reason = stream_acc.ollama_done_reason
    reasoning_guard_triggered = stream_acc.reasoning_guard_triggered
    stream_latency_ms = int((time.time() - stream_start_time) * 1000)
    budget_error = _output_budget_exhaustion_error(ctx.trace, ollama_done_payload)
    if append_budget_error_chunks(stream_acc, budget_error):
        yield sse_content_chunk(oid, ctx.client_visible_model, budget_error)
        full_content = stream_acc.visible_content
        final_content = stream_acc.final_content

    tool_resolution = resolve_native_stream_tool_calls(
        tool_calls_raw=tool_calls_raw,
        reasoning_content=reasoning_content,
        final_content=final_content,
        full_content=full_content,
        ollama_done_reason=ollama_done_reason,
        budget_error=budget_error,
        reasoning_guard_triggered=reasoning_guard_triggered,
    )
    mapped_calls = tool_resolution.mapped_calls
    tool_calls_recovered_from_text = tool_resolution.tool_calls_recovered_from_text
    reasoning_content = tool_resolution.reasoning_content
    final_content = tool_resolution.final_content
    full_content = tool_resolution.full_content
    finish_reason = tool_resolution.finish_reason
    if tool_calls_recovered_from_text:
        _append_trace_warning(ctx.trace, "native_tool_calls_recovered_from_text")

    if tool_resolution.has_tool_calls:
        gemini_upserted = _persist_gemini_tool_calls_state(
            tool_calls=mapped_calls,
            model_name=ctx.use_model,
            trace_id=ctx.trace_id,
            db_path=ctx.proxy_db_path,
        )
        if mapped_calls:
            payload_calls = _sse_tool_calls_payload(mapped_calls)
            yield (
                f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': ctx.client_visible_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_calls}, 'finish_reason': None}]})}\n\n"
            )
    else:
        gemini_upserted = 0

    yield from iter_sse_finish_with_done(oid, ctx.client_visible_model, finish_reason)

    stream_tokens = build_stream_trace_token_estimates(
        prompt_tokens=estimate_prompt_tokens_from_messages_json(
            ctx.native_ollama_messages_for_upstream,
        ),
        completion_tokens=max(1, int(len(full_content) / 4)),
    )
    prompt_tokens = stream_tokens.prompt_tokens
    completion_tokens = stream_tokens.completion_tokens
    total_tokens_holder[0] = stream_tokens.total_tokens

    ctx.trace["ollama"]["chat_stream"] = True
    ctx.trace["ollama"]["tokens_estimates"] = build_ollama_stream_token_estimates_dict(stream_tokens)
    ctx.trace["response"] = build_native_tools_stream_response_base(
        stream_latency_ms=stream_latency_ms,
        mapped_calls_count=len(mapped_calls),
        tool_calls_raw_count=len(tool_calls_raw),
        reasoning_guard_triggered=reasoning_guard_triggered,
        ollama_metrics=_trace_ollama_api_metrics(ollama_done_payload, model_id=ctx.use_model),
    )
    record_reasoning_token_estimates(ctx.trace["response"], reasoning_content, final_content)
    _apply_trace_response_text_fields(
        ctx.trace["response"],
        visible_content=full_content,
        reasoning_content=reasoning_content,
        final_content=final_content,
        log_preview=ctx.log_preview,
    )
    _apply_response_diagnostics(ctx.trace)
    ctx.trace["response"].update(
        native_tools_stream_trace_response_extras(
            gemini_upserted=gemini_upserted,
            tool_calls_raw=tool_calls_raw,
            mapped_calls=mapped_calls,
            tool_calls_recovered_from_text=tool_calls_recovered_from_text,
        )
    )
    ctx.trace["steps"].append(
        build_provider_stream_step(
            name="provider_chat_native_tools_stream",
            duration_ms=stream_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )
    ctx.publish_response_artifacts(
        visible_content=full_content,
        reasoning_content=reasoning_content,
        final_content=final_content,
    )
    ctx.publish_trace(ctx.trace)

    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request (native tools stream): {ctx.user_query[:100]}...",
            response_preview=full_content,
            latency_ms_value=stream_latency_ms,
            trace_payload=ctx.trace,
            stream_value=True,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=prompt_tokens,
            completion_tokens_value=completion_tokens,
            total_tokens_value=total_tokens_holder[0],
            ollama_chat_stream=True,
            warn_label="native-tools stream",
        )
        _RAG_LOG.debug(
            json.dumps(
                ctx.rag_request_completed_payload(
                    user_query=ctx.user_query,
                    trace_id=ctx.trace_id,
                    use_model=ctx.use_model,
                    requested_model=ctx.requested_model,
                    latency_ms=stream_latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    rag_context_for_obs=ctx.rag_ctx_for_log,
                    rag_timings=ctx.rag_timings,
                    trace=ctx.trace,
                    stream=True,
                    is_autocomplete=bool(ctx.is_autocomplete),
                    native_tools=True,
                )
            )
        )

    ctx.w.set_proxy_status(ctx.w.status_idle)
    ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)
    ctx.w.set_latest_request_total_tokens(total_tokens_holder[0])


def iter_native_tools_single_sse_stream(ctx: NativeToolsSingleStreamContext) -> Iterator[str]:
    oid = stream_completion_id()
    tool_payload = _sse_tool_calls_payload(ctx.tool_calls_out) if ctx.tool_calls_out else None
    yield from iter_sse_single_shot_assistant(
        oid,
        ctx.client_visible_model,
        content=ctx.content_str,
        reasoning_content=str(ctx.content_parts.get("reasoning_content") or ""),
        tool_calls_payload=tool_payload,
        finish_reason=ctx.finish,
        include_reasoning_content=ctx.include_reasoning_content,
    )

    ctx.trace["ollama"]["chat_stream"] = False
    ctx.trace["steps"].append(
        {
            "name": "provider_chat_native_tools_sse_single",
            "duration_ms": int(ctx.latency_ms),
            "tokens_in_est": ctx.prompt_tokens,
            "tokens_out_est": ctx.completion_tokens,
        }
    )
    ctx.publish_response_artifacts(
        visible_content=ctx.content_parts["visible_content"] or ctx.content_str,
        reasoning_content=ctx.content_parts["reasoning_content"],
        final_content=ctx.content_parts["final_content"],
    )
    ctx.publish_trace(ctx.trace)
    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request (native tools SSE single): {ctx.user_query[:100]}...",
            response_preview=(ctx.content_str or ""),
            latency_ms_value=ctx.latency_ms,
            trace_payload=ctx.trace,
            stream_value=True,
            include_rag_fields=False,
            include_token_fields=False,
            ollama_chat_stream=False,
            sse_single_chunk=True,
            warn_label="native-tools SSE single",
        )
    ctx.w.set_proxy_status(ctx.w.status_idle)
    ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)
    ctx.w.set_latest_request_total_tokens(ctx.prompt_tokens + ctx.completion_tokens)


def iter_legacy_tool_call_sse_stream(ctx: LegacyToolCallStreamContext) -> Iterator[str]:
    oid = stream_completion_id()
    yield from iter_sse_tool_calls_response(
        oid,
        ctx.client_visible_model,
        [
            {
                "index": 0,
                "id": ctx.tool_call["id"],
                "type": "function",
                "function": {
                    "name": ctx.selected_edit_tool_name,
                    "arguments": ctx.tool_call["function"]["arguments"],
                },
            }
        ],
    )


def iter_legacy_plain_text_sse_stream(ctx: LegacyPlainTextStreamContext) -> Iterator[str]:
    oid = stream_completion_id()
    yield from iter_sse_plain_content_response(oid, ctx.client_visible_model, ctx.tool_plain_fallback)


def iter_standard_sse_stream(ctx: StandardStreamContext) -> Iterator[str]:
    oid = stream_completion_id()
    stream_start_time = time.time()
    stream_acc = StreamContentAccumulator()
    reasoning_guard_limit_chars = reasoning_guard_limit_from_env()
    total_tokens_holder = [0]

    yield sse_role_assistant_chunk(oid, ctx.client_visible_model)

    def _on_reasoning_guard() -> None:
        _append_trace_warning(ctx.trace, "reasoning_only_guard_triggered")
        ctx.trace["request"]["reasoning_only_guard_chars"] = reasoning_guard_limit_chars

    try:
        _apply_provider_trace_fields(
            ctx.trace,
            ctx.chat_client,
            model_id=ctx.use_model,
            operation="chat_api_stream_events",
        )
        yield from iter_sse_from_ollama_stream_events(
            _iter_proxy_ollama_chat_stream(
                ctx.chat_client,
                ctx.ollama_messages,
                ctx.use_model,
                ctx.ollama_think,
                options_overlay=ctx.ollama_options_overlay(),
            ),
            completion_id=oid,
            client_visible_model=ctx.client_visible_model,
            include_reasoning_content=ctx.include_reasoning_content,
            accumulator=stream_acc,
            reasoning_guard_limit_chars=reasoning_guard_limit_chars,
            on_reasoning_guard=_on_reasoning_guard,
        )
    except Exception as exc:
        if not ctx.private_build:
            ctx.w.log_webui_error("rag_routes.chat_completions", exc, {"stage": "stream_chat"})
        ctx.log_rag_error_private("stream_chat", exc, private_build=ctx.private_build)
        err_text = upstream_chat_error_message(exc, ctx.trace, model=ctx.use_model)
        stream_acc.visible_parts.append(err_text)
        stream_acc.final_parts.append(err_text)
        yield sse_content_chunk(oid, ctx.client_visible_model, err_text)

    full_response = stream_acc.visible_content
    reasoning_content = stream_acc.reasoning_content
    final_content = stream_acc.final_content
    ollama_done_payload = stream_acc.ollama_done_payload
    ollama_done_reason = stream_acc.ollama_done_reason
    reasoning_guard_triggered = stream_acc.reasoning_guard_triggered
    budget_error = _output_budget_exhaustion_error(ctx.trace, ollama_done_payload)
    if budget_error:
        yield sse_content_chunk(oid, ctx.client_visible_model, budget_error)
        full_response, final_content = apply_standard_stream_budget_to_content(
            full_response,
            final_content,
            budget_error,
        )

    full_response, final_content, empty_fallback = apply_stream_empty_response_fallback(
        full_response,
        final_content,
    )
    if empty_fallback:
        yield sse_content_chunk(oid, ctx.client_visible_model, full_response)

    finish_reason = resolve_stream_finish_reason(
        ollama_done_reason=ollama_done_reason,
        budget_error=budget_error,
        reasoning_guard_triggered=reasoning_guard_triggered,
    )
    yield from iter_sse_finish_with_done(oid, ctx.client_visible_model, finish_reason)

    stream_latency_ms = int((time.time() - stream_start_time) * 1000)

    stream_tokens = build_stream_trace_token_estimates(
        prompt_tokens=estimate_prompt_tokens_from_ollama_messages(ctx.ollama_messages),
        completion_tokens=approx_token_count(full_response),
    )
    prompt_tokens_approx = stream_tokens.prompt_tokens
    completion_tokens_approx = stream_tokens.completion_tokens
    total_tokens_approx = stream_tokens.total_tokens
    total_tokens_holder[0] = total_tokens_approx

    ctx.trace["ollama"]["chat_stream"] = True
    ctx.trace["ollama"]["tokens_estimates"] = build_ollama_stream_token_estimates_dict(stream_tokens)
    ctx.trace["response"] = build_standard_stream_response_base(
        stream_latency_ms=stream_latency_ms,
        reasoning_guard_triggered=reasoning_guard_triggered,
        ollama_metrics=_trace_ollama_api_metrics(ollama_done_payload, model_id=ctx.use_model),
    )
    record_reasoning_token_estimates(ctx.trace["response"], reasoning_content, final_content)
    _apply_trace_response_text_fields(
        ctx.trace["response"],
        visible_content=full_response,
        reasoning_content=reasoning_content,
        final_content=final_content,
        log_preview=ctx.log_preview,
    )
    _apply_response_diagnostics(ctx.trace)
    ctx.trace["steps"].append(
        build_provider_stream_step(
            name="provider_chat_stream",
            duration_ms=stream_latency_ms,
            prompt_tokens=prompt_tokens_approx,
            completion_tokens=completion_tokens_approx,
        )
    )
    ctx.publish_response_artifacts(
        visible_content=full_response,
        reasoning_content=reasoning_content,
        final_content=final_content,
    )
    ctx.publish_trace(ctx.trace)

    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request (stream): {ctx.user_query[:100]}...",
            response_preview=full_response,
            latency_ms_value=stream_latency_ms,
            trace_payload=ctx.trace,
            stream_value=True,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=prompt_tokens_approx,
            completion_tokens_value=completion_tokens_approx,
            total_tokens_value=total_tokens_approx,
            ollama_chat_stream=True,
            warn_label="stream",
        )

        _RAG_LOG.debug(
            json.dumps(
                ctx.rag_request_completed_payload(
                    user_query=ctx.user_query,
                    trace_id=ctx.trace_id,
                    use_model=ctx.use_model,
                    requested_model=ctx.requested_model,
                    latency_ms=stream_latency_ms,
                    prompt_tokens=prompt_tokens_approx,
                    completion_tokens=completion_tokens_approx,
                    rag_context_for_obs=ctx.rag_ctx_for_log,
                    rag_timings=ctx.rag_timings,
                    trace=ctx.trace,
                    stream=True,
                    is_autocomplete=bool(ctx.is_autocomplete),
                    native_tools=False,
                )
            )
        )
        _RAG_LOG.debug(
            "RAG response (stream) model=%s len=%s preview=%s",
            ctx.use_model,
            len(full_response),
            full_response[: ctx.log_preview] if full_response else "",
        )

    ctx.w.set_proxy_status(ctx.w.status_idle)
    ctx.w.set_latest_request_seconds(time.time() - ctx.start_time)
    ctx.w.set_latest_request_total_tokens(total_tokens_holder[0] or None)


def iter_plain_single_sse_stream(ctx: PlainSingleStreamContext) -> Iterator[str]:
    tool_payload = _sse_tool_calls_payload(ctx.tool_calls) if ctx.tool_calls else None
    yield from iter_sse_single_shot_assistant(
        ctx.response_id,
        ctx.client_visible_model,
        content=str(ctx.content or ""),
        reasoning_content=str(ctx.content_parts.get("reasoning_content") or ""),
        tool_calls_payload=tool_payload,
        finish_reason=ctx.finish_reason,
        include_reasoning_content=ctx.include_reasoning_content,
    )
    if not ctx.private_build:
        ctx.persist_proxy_request_log(
            message=f"Proxy request (SSE single): {ctx.user_query[:100]}...",
            response_preview=ctx.content_preview,
            latency_ms_value=ctx.latency_ms,
            trace_payload=ctx.trace,
            stream_value=True,
            include_rag_fields=True,
            include_token_fields=True,
            prompt_tokens_value=ctx.prompt_tokens_approx,
            completion_tokens_value=ctx.completion_tokens_approx,
            total_tokens_value=ctx.total_tokens_approx,
            ollama_chat_stream=False,
            sse_single_chunk=True,
            warn_label="SSE single",
        )
