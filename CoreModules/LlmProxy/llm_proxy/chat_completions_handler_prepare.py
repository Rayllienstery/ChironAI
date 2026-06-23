"""Message preparation, vision fallback, and tool-limit response for chat completions handler."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from flask import Response, jsonify

from llm_proxy.chat_completions_ollama_proxy import (
    _apply_trace_response_text_fields,
    _ollama_message_content_str,
    _trace_ollama_messages_for_ui,
)
from llm_proxy.chat_completions_ollama_proxy import (
    ollama_messages_have_images as _ollama_messages_have_images,
)
from llm_proxy.chat_completions_ollama_proxy import (
    vision_fallback_preferences as _vision_fallback_preferences,
)
from llm_proxy.chat_completions_rag_prep import (
    build_rag_metadata_for_response,
)
from llm_proxy.chat_completions_response_helpers import (
    record_reasoning_token_estimates as _record_reasoning_token_estimates,
)
from llm_proxy.chat_completions_response_helpers import (
    tool_loop_limit_final_message as _tool_loop_limit_final_message,
)
from llm_proxy.chat_completions_sse_generators import (
    ToolLimitStreamContext,
    iter_tool_limit_sse_stream,
)
from llm_proxy.chat_completions_streaming import (
    SSE_MIMETYPE as _SSE_MIMETYPE,
)
from llm_proxy.chat_completions_streaming import (
    SSE_RESPONSE_HEADERS as _SSE_RESPONSE_HEADERS,
)
from llm_proxy.chat_completions_upstream_budget import (
    compact_upstream_messages_for_budget,
)
from llm_proxy.ollama_compat import (
    caps_supports_thinking,
    caps_supports_vision,
    find_cached_ollama_vision_model,
    get_cached_ollama_capabilities,
)


class PreparedMessagesResult:
    __slots__ = (
        "ollama_messages",
        "use_model",
        "client_visible_model",
        "ollama_think",
        "_ollama_caps",
        "ollama_messages_have_images",
        "early_return",
    )

    def __init__(
        self,
        *,
        ollama_messages: list[dict[str, Any]],
        use_model: str,
        client_visible_model: str,
        ollama_think: bool | str | None,
        _ollama_caps: frozenset[str] | None,
        ollama_messages_have_images: bool,
        early_return: Response | tuple[Response, int] | None = None,
    ) -> None:
        self.ollama_messages = ollama_messages
        self.use_model = use_model
        self.client_visible_model = client_visible_model
        self.ollama_think = ollama_think
        self._ollama_caps = _ollama_caps
        self.ollama_messages_have_images = ollama_messages_have_images
        self.early_return = early_return


def prepare_messages_and_handle_tool_limit(
    *,
    w: Any,
    trace: dict[str, Any],
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    actual_model: str,
    stream: bool,
    reasoning_for_prompt: Any,
    effective_rag_repo: Any,
    effective_embed_provider: Any,
    effective_rerank_client: Any,
    effective_prefix: str,
    effective_suffix: str,
    effective_context_chunk_chars: int,
    effective_context_total_chars: int,
    effective_confidence_threshold: float,
    effective_ollama_model: str,
    rag_keywords: Any,
    rag_ctx_for_log: Any,
    force_rag: bool,
    use_native_tools: bool,
    web_supplement_text: str,
    autocomplete_id: str,
    input_budget: int | None,
    ollama_think: bool | str | None,
    ollama_chat_url: str | None,
    _ollama_caps: frozenset[str] | None,
    active_build: dict[str, Any] | None,
    dumb_build_pipeline: bool,
    requested_model: str,
    is_autocomplete: bool,
    tool_choice_effective: Any,
    tools: list[dict[str, Any]],
    tool_loop_limit_reached: bool,
    include_rag_metadata: bool,
    include_reasoning_content: bool,
    private_build: bool,
    user_query: str,
    log_preview: int,
    start_time: float,
    rag_ctx: Any,
    rag_timings: Any,
    latency_ms: int,
    prompt_tokens_approx: int,
    completion_tokens_approx: int,
    publish_trace: Callable[[dict[str, Any]], None],
    publish_response_artifacts: Callable[..., None],
    persist_proxy_request_log: Callable[..., None],
    log_rag_error_private: Callable[..., None],
    _append_trace_warning: Callable[..., None],
) -> PreparedMessagesResult:
    rag_ctx_resolved = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
    try:
        req = w.rag_question_request_factory(
            messages=messages,
            model=actual_model,
            stream=stream,
            reasoning_level=reasoning_for_prompt,
        )
        ollama_messages, use_model = w.prepare_ollama_messages(
            req,
            effective_rag_repo,
            effective_embed_provider,
            effective_rerank_client,
            effective_prefix,
            effective_suffix,
            effective_context_chunk_chars,
            effective_context_total_chars,
            effective_confidence_threshold,
            effective_ollama_model,
            reasoning_level=reasoning_for_prompt,
            rag_required_keywords=rag_keywords,
            rag_context=rag_ctx_for_log,
            trigger_threshold=None,
            force_rag=force_rag,
            native_tools=use_native_tools,
            web_supplement=web_supplement_text,
        )
        if use_model == autocomplete_id:
            use_model = effective_ollama_model

        if input_budget is not None:
            ollama_messages, compact_diag = compact_upstream_messages_for_budget(
                ollama_messages,
                input_budget,
            )
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["model"] = use_model
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["think"] = ollama_think
        trace["ollama"]["chat_stream"] = False
        ollama_messages_have_images = _ollama_messages_have_images(ollama_messages)
        image_model_caps: frozenset[str] | None = _ollama_caps
        if ollama_messages_have_images and ollama_chat_url:
            try:
                image_model_caps = get_cached_ollama_capabilities(use_model, ollama_chat_url)
            except Exception:
                image_model_caps = None
            if image_model_caps is not None:
                _ollama_caps = image_model_caps
                trace["request"]["ollama_capabilities"] = sorted(image_model_caps)
            if image_model_caps is not None and not caps_supports_vision(image_model_caps):
                fallback_model = find_cached_ollama_vision_model(
                    ollama_chat_url,
                    preferred_models=_vision_fallback_preferences(active_build),
                )
                if fallback_model and fallback_model != use_model:
                    original_use_model = use_model
                    use_model = fallback_model
                    effective_ollama_model = fallback_model
                    fallback_caps = get_cached_ollama_capabilities(fallback_model, ollama_chat_url)
                    if fallback_caps is not None:
                        image_model_caps = fallback_caps
                        _ollama_caps = fallback_caps
                        trace["request"]["ollama_capabilities"] = sorted(fallback_caps)
                        if ollama_think is not None and not caps_supports_thinking(fallback_caps):
                            ollama_think = None
                            trace["request"]["ollama_think"] = None
                            trace["request"]["vision_fallback_stripped_think"] = True
                    trace["request"]["actual_model"] = use_model
                    trace["request"]["vision_model_fallback"] = {
                        "from": original_use_model,
                        "to": use_model,
                        "reason": "selected_ollama_model_lacks_vision",
                    }
                    trace["ollama"]["model"] = use_model
                    trace["ollama"]["think"] = ollama_think
                    _append_trace_warning(trace, "vision_model_fallback")
        trace["request"]["use_native_tools"] = use_native_tools
        trace["request"]["tool_choice_effective"] = (
            tool_choice_effective
            if isinstance(tool_choice_effective, (str, dict))
            else str(tool_choice_effective)
        )
        trace["request"]["tools_count_effective"] = (
            len(tools) if use_native_tools and tool_choice_effective != "none" else 0
        )
        if use_native_tools and ollama_messages_have_images:
            trace["request"]["native_tools_preserved_for_vision"] = True
        client_visible_model = requested_model if dumb_build_pipeline else use_model

        if tool_loop_limit_reached:
            content = _tool_loop_limit_final_message(trace) or (
                "[Error: max_agent_steps limit reached. Tools were disabled for this turn.]"
            )
            _append_trace_warning(trace, "tool_loop_limit_response_forced")
            _latency_ms = int((time.time() - start_time) * 1000)
            _prompt_text = " ".join(
                _ollama_message_content_str(m.get("content"))
                for m in ollama_messages
                if isinstance(m, dict)
            )
            _prompt_tokens_approx = max(1, int(len(_prompt_text) / 4))
            _completion_tokens_approx = max(1, int(len(content) / 4))
            _total_tokens_approx = _prompt_tokens_approx + _completion_tokens_approx
            w.set_proxy_status(w.status_idle)
            w.set_latest_request_seconds(time.time() - start_time)
            w.set_latest_request_total_tokens(_total_tokens_approx)
            trace["ollama"]["chat_skipped"] = "tool_loop_limit_reached"
            trace["ollama"]["tokens_estimates"] = {
                "prompt_tokens_estimated": _prompt_tokens_approx,
                "completion_tokens_estimated": _completion_tokens_approx,
                "total_tokens_estimated": _total_tokens_approx,
            }
            trace["response"] = {
                "latency_ms": _latency_ms,
                "tool_calls_count": 0,
            }
            _record_reasoning_token_estimates(trace["response"], "", content)
            _apply_trace_response_text_fields(
                trace["response"],
                visible_content=content,
                reasoning_content="",
                final_content=content,
                log_preview=log_preview,
            )
            trace["steps"].append(
                {
                    "name": "tool_loop_limit_response",
                    "duration_ms": _latency_ms,
                    "tokens_in_est": _prompt_tokens_approx,
                    "tokens_out_est": _completion_tokens_approx,
                }
            )
            publish_response_artifacts(
                visible_content=content,
                reasoning_content="",
                final_content=content,
            )
            publish_trace(trace)
            response_data: dict[str, object] = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion",
                "created": 0,
                "model": client_visible_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            }
            if include_rag_metadata and rag_ctx_resolved:
                response_data["rag_metadata"] = build_rag_metadata_for_response(rag_ctx_resolved)

            if stream:
                rid = str(response_data["id"])

                early = Response(
                    iter_tool_limit_sse_stream(
                        ToolLimitStreamContext(
                            response_id=rid,
                            client_visible_model=client_visible_model,
                            content=content,
                            private_build=private_build,
                            user_query=user_query,
                            log_preview=log_preview,
                            latency_ms=_latency_ms,
                            trace=trace,
                            prompt_tokens_approx=_prompt_tokens_approx,
                            completion_tokens_approx=_completion_tokens_approx,
                            total_tokens_approx=_total_tokens_approx,
                            persist_proxy_request_log=persist_proxy_request_log,
                        )
                    ),
                    mimetype=_SSE_MIMETYPE,
                    headers=_SSE_RESPONSE_HEADERS,
                )
                return PreparedMessagesResult(
                    ollama_messages=ollama_messages,
                    use_model=use_model,
                    client_visible_model=client_visible_model,
                    ollama_think=ollama_think,
                    _ollama_caps=_ollama_caps,
                    ollama_messages_have_images=ollama_messages_have_images,
                    early_return=early,
                )

            if not private_build:
                persist_proxy_request_log(
                    message=f"Proxy request (tool limit): {user_query[:100]}...",
                    response_preview=content[:log_preview],
                    latency_ms_value=_latency_ms,
                    trace_payload=trace,
                    stream_value=False,
                    include_rag_fields=True,
                    include_token_fields=True,
                    prompt_tokens_value=_prompt_tokens_approx,
                    completion_tokens_value=_completion_tokens_approx,
                    total_tokens_value=_total_tokens_approx,
                    extra_metadata={"tool_loop_limit_response": True},
                    warn_label="tool limit",
                )
            return PreparedMessagesResult(
                ollama_messages=ollama_messages,
                use_model=use_model,
                client_visible_model=client_visible_model,
                ollama_think=ollama_think,
                _ollama_caps=_ollama_caps,
                ollama_messages_have_images=ollama_messages_have_images,
                early_return=(jsonify(response_data), 200),
            )
    except Exception as e:
        if not private_build:
            w.log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
        log_rag_error_private("prepare_rag", e, private_build=private_build)
        return PreparedMessagesResult(
            ollama_messages=[],
            use_model="",
            client_visible_model="",
            ollama_think=None,
            _ollama_caps=None,
            ollama_messages_have_images=False,
            early_return=(jsonify({"error": str(e)}), 500),
        )

    return PreparedMessagesResult(
        ollama_messages=ollama_messages,
        use_model=use_model,
        client_visible_model=client_visible_model,
        ollama_think=ollama_think,
        _ollama_caps=_ollama_caps,
        ollama_messages_have_images=ollama_messages_have_images,
        early_return=None,
    )
