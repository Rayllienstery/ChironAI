"""Response dispatch paths extracted from chat_completions_handler (native tools, legacy tools, standard)."""

from __future__ import annotations

from typing import Any, Callable

from flask import Response

from llm_proxy.chat_completions_gemini_native import (
    _interpolate_native_tools_for_gemini,
    _preflight_native_tool_messages,
    _preflight_native_tools_payload,
)
from llm_proxy.chat_completions_legacy_tool_stream import (
    LegacyToolStreamContext,
    is_legacy_tool_stream_mode,
    try_build_legacy_tool_stream_response,
)
from llm_proxy.chat_completions_native_tools_nonstream import (
    NativeToolsNonStreamContext,
    try_build_native_tools_nonstream_response,
)
from llm_proxy.chat_completions_nonstream_response import (
    StandardNonStreamContext,
    build_standard_nonstream_response,
)
from llm_proxy.chat_completions_ollama_proxy import (
    _trace_ollama_messages_for_ui,
)
from llm_proxy.chat_completions_response_helpers import (
    with_initial_system_message as _with_initial_system_message,
)
from llm_proxy.chat_completions_run_phases import (
    _tool_loop_needs_finalize_nudge,
)
from llm_proxy.chat_completions_sse_generators import (
    NativeToolsStreamContext,
    StandardStreamContext,
    iter_native_tools_sse_stream,
    iter_standard_sse_stream,
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
    ollama_tools_from_openai,
)
from llm_proxy.tool_helpers import (
    _build_tool_json_instruction,
    _client_files_snippet,
    _client_selection_snippet,
    _workspace_selection_snippet,
)


def dispatch_response(
    *,
    w: Any,
    trace: dict[str, Any],
    use_native_tools: bool,
    tools: list[dict[str, Any]],
    tool_choice_effective: Any,
    use_model: str,
    ollama_messages: list[dict[str, Any]],
    ollama_think: bool | str | None,
    ollama_messages_have_images: bool,
    input_budget: int | None,
    trace_id: str,
    proxy_db_path: str,
    has_tool_result: bool,
    tool_result_indicates_failure: bool,
    tool_loop_stats: Any,
    stream: bool,
    build_sse_streaming: bool,
    private_build: bool,
    client_visible_model: str,
    chat_client: Any,
    include_reasoning_content: bool,
    include_rag_metadata: bool,
    user_query: str,
    log_preview: int,
    start_time: float,
    rag_ctx: Any,
    rag_ctx_for_log: Any,
    rag_timings: Any,
    requested_model: str,
    is_autocomplete: bool,
    post_tool_success_turn: bool,
    selected_edit_tool_name: str | None,
    selected_edit_tool: dict[str, Any] | None,
    selected_tool_write_capable: bool,
    last_user: str,
    ollama_options_overlay: Callable[[], dict[str, Any] | None],
    publish_trace: Callable[[dict[str, Any]], None],
    publish_response_artifacts: Callable[..., None],
    persist_proxy_request_log: Callable[..., None],
    log_rag_error_private: Callable[..., None],
    rag_request_completed_payload: Callable[..., Any],
) -> Response | tuple[Response, int] | None:
    if use_native_tools:
        trace["request"]["native_tools"] = True
        native_tools_diag: dict[str, Any] = {}
        native_tools_input = list(tools)
        native_tools_input, interpolation_diag = _interpolate_native_tools_for_gemini(
            native_tools_input,
            model_name=use_model,
        )
        if interpolation_diag:
            native_tools_diag.update(interpolation_diag)
        native_tools_payload, tools_diag = _preflight_native_tools_payload(native_tools_input)
        if tools_diag:
            native_tools_diag.update(tools_diag)
        oll_tools = ollama_tools_from_openai(native_tools_payload)
        native_ollama_messages, messages_diag = _preflight_native_tool_messages(
            ollama_messages,
            model_name=use_model,
            trace_id=trace_id,
            db_path=proxy_db_path,
        )
        if messages_diag:
            native_tools_diag.update(messages_diag)

        native_ollama_messages, compact_diag = compact_upstream_messages_for_budget(
            native_ollama_messages,
            input_budget,
        )
        if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
            native_tools_diag["upstream_context_compaction"] = compact_diag

        native_ollama_messages_for_upstream = native_ollama_messages
        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        trace["ollama"]["tools"] = list(oll_tools) if isinstance(oll_tools, list) else []
        if (
            has_tool_result
            and not tool_result_indicates_failure
            and _tool_loop_needs_finalize_nudge(tool_loop_stats)
        ):
            native_ollama_messages = _with_initial_system_message(
                native_ollama_messages,
                (
                    "You have already completed multiple consecutive tool rounds of the same type. "
                    "Prefer synthesizing the final answer now, and call another tool only if a concrete blocker remains."
                ),
            )
            native_tools_diag["tool_loop_finalize_nudge"] = True
            native_ollama_messages_for_upstream = native_ollama_messages
            trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(native_ollama_messages_for_upstream)
        if native_tools_diag:
            trace["request"]["native_tools_preflight"] = native_tools_diag

        if stream and build_sse_streaming:
            w.set_proxy_status(w.status_response)
            trace["request"]["ollama_stream_timeout_disabled"] = True

            return Response(
                iter_native_tools_sse_stream(
                    NativeToolsStreamContext(
                        w=w,
                        trace=trace,
                        private_build=private_build,
                        client_visible_model=client_visible_model,
                        chat_client=chat_client,
                        native_ollama_messages_for_upstream=native_ollama_messages_for_upstream,
                        use_model=use_model,
                        ollama_think=ollama_think,
                        oll_tools=oll_tools,
                        tool_choice_effective=tool_choice_effective,
                        include_reasoning_content=include_reasoning_content,
                        user_query=user_query,
                        trace_id=trace_id,
                        proxy_db_path=proxy_db_path,
                        log_preview=log_preview,
                        start_time=start_time,
                        rag_ctx_for_log=rag_ctx_for_log,
                        rag_timings=rag_timings,
                        requested_model=requested_model,
                        is_autocomplete=is_autocomplete,
                        ollama_options_overlay=ollama_options_overlay,
                        publish_trace=publish_trace,
                        publish_response_artifacts=publish_response_artifacts,
                        persist_proxy_request_log=persist_proxy_request_log,
                        log_rag_error_private=log_rag_error_private,
                        rag_request_completed_payload=rag_request_completed_payload,
                    )
                ),
                mimetype=_SSE_MIMETYPE,
                headers=_SSE_RESPONSE_HEADERS,
            )

        return try_build_native_tools_nonstream_response(
            NativeToolsNonStreamContext(
                w=w,
                trace=trace,
                private_build=private_build,
                stream=bool(stream),
                client_visible_model=client_visible_model,
                chat_client=chat_client,
                native_ollama_messages=native_ollama_messages,
                native_ollama_messages_for_upstream=native_ollama_messages_for_upstream,
                use_model=use_model,
                ollama_think=ollama_think,
                oll_tools=oll_tools,
                tool_choice_effective=tool_choice_effective,
                include_reasoning_content=include_reasoning_content,
                include_rag_metadata=bool(include_rag_metadata),
                user_query=user_query,
                trace_id=trace_id,
                proxy_db_path=proxy_db_path,
                log_preview=log_preview,
                start_time=start_time,
                rag_ctx=rag_ctx,
                rag_ctx_for_log=rag_ctx_for_log,
                rag_timings=rag_timings,
                requested_model=requested_model,
                is_autocomplete=is_autocomplete,
                post_tool_success_turn=post_tool_success_turn,
                native_tools_diag=native_tools_diag,
                ollama_options_overlay=ollama_options_overlay,
                publish_trace=publish_trace,
                publish_response_artifacts=publish_response_artifacts,
                persist_proxy_request_log=persist_proxy_request_log,
                log_rag_error_private=log_rag_error_private,
                rag_request_completed_payload=rag_request_completed_payload,
            )
        )

    if tools and tool_choice_effective != "none":
        if not post_tool_success_turn:
            tool_json_instruction = _build_tool_json_instruction(
                selected_edit_tool_name, selected_edit_tool
            )
            if tool_json_instruction:
                ollama_messages = _with_initial_system_message(ollama_messages, tool_json_instruction)
            excerpt_sys = _workspace_selection_snippet(user_query or last_user or "").strip()
            if not excerpt_sys:
                excerpt_sys = (
                    _client_selection_snippet(user_query or last_user or "").strip()
                    or _client_files_snippet(user_query or last_user or "").strip()
                )
            if excerpt_sys:
                ollama_messages = _with_initial_system_message(ollama_messages, excerpt_sys)

        if input_budget is not None:
            ollama_messages, compact_diag = compact_upstream_messages_for_budget(
                ollama_messages,
                input_budget,
            )
            if compact_diag.get("compacted") or compact_diag.get("still_over_budget_after_history_compaction"):
                trace["request"]["upstream_context_compaction"] = compact_diag

        trace["ollama"]["messages"] = _trace_ollama_messages_for_ui(ollama_messages)
        trace["ollama"]["model"] = use_model
        publish_trace(trace)

    if is_legacy_tool_stream_mode(
        stream=stream,
        tools=tools,
        tool_choice_effective=tool_choice_effective,
        post_tool_success_turn=post_tool_success_turn,
    ):
        legacy_tool_response = try_build_legacy_tool_stream_response(
            LegacyToolStreamContext(
                w=w,
                trace=trace,
                trace_id=trace_id,
                private_build=private_build,
                client_visible_model=client_visible_model,
                chat_client=chat_client,
                ollama_messages=ollama_messages,
                use_model=use_model,
                ollama_think=ollama_think,
                user_query=user_query,
                log_preview=log_preview,
                start_time=start_time,
                rag_ctx_for_log=rag_ctx_for_log,
                rag_timings=rag_timings,
                requested_model=requested_model,
                is_autocomplete=is_autocomplete,
                selected_edit_tool_name=selected_edit_tool_name,
                selected_edit_tool=selected_edit_tool,
                selected_tool_write_capable=selected_tool_write_capable,
                ollama_options_overlay=ollama_options_overlay,
                publish_trace=publish_trace,
                publish_response_artifacts=publish_response_artifacts,
                persist_proxy_request_log=persist_proxy_request_log,
                log_rag_error_private=log_rag_error_private,
                rag_request_completed_payload=rag_request_completed_payload,
            )
        )
        if legacy_tool_response is not None:
            return legacy_tool_response

    if stream and build_sse_streaming:
        w.set_proxy_status(w.status_response)

        return Response(
            iter_standard_sse_stream(
                StandardStreamContext(
                    w=w,
                    trace=trace,
                    trace_id=trace_id,
                    private_build=private_build,
                    client_visible_model=client_visible_model,
                    chat_client=chat_client,
                    ollama_messages=ollama_messages,
                    use_model=use_model,
                    ollama_think=ollama_think,
                    include_reasoning_content=include_reasoning_content,
                    user_query=user_query,
                    log_preview=log_preview,
                    start_time=start_time,
                    rag_ctx_for_log=rag_ctx_for_log,
                    rag_timings=rag_timings,
                    requested_model=requested_model,
                    is_autocomplete=is_autocomplete,
                    ollama_options_overlay=ollama_options_overlay,
                    publish_trace=publish_trace,
                    publish_response_artifacts=publish_response_artifacts,
                    persist_proxy_request_log=persist_proxy_request_log,
                    log_rag_error_private=log_rag_error_private,
                    rag_request_completed_payload=rag_request_completed_payload,
                )
            ),
            mimetype=_SSE_MIMETYPE,
            headers=_SSE_RESPONSE_HEADERS,
        )
    return build_standard_nonstream_response(
        StandardNonStreamContext(
            w=w,
            trace=trace,
            private_build=private_build,
            stream=bool(stream),
            build_sse_streaming=build_sse_streaming,
            client_visible_model=client_visible_model,
            chat_client=chat_client,
            ollama_messages=ollama_messages,
            use_model=use_model,
            ollama_think=ollama_think,
            include_reasoning_content=include_reasoning_content,
            include_rag_metadata=bool(include_rag_metadata),
            user_query=user_query,
            trace_id=trace_id,
            log_preview=log_preview,
            start_time=start_time,
            rag_ctx=rag_ctx,
            rag_ctx_for_log=rag_ctx_for_log,
            rag_timings=rag_timings,
            requested_model=requested_model,
            is_autocomplete=is_autocomplete,
            tools=tools,
            tool_choice_effective=tool_choice_effective,
            post_tool_success_turn=post_tool_success_turn,
            selected_edit_tool_name=selected_edit_tool_name,
            selected_edit_tool=selected_edit_tool,
            selected_tool_write_capable=selected_tool_write_capable,
            ollama_options_overlay=ollama_options_overlay,
            publish_trace=publish_trace,
            publish_response_artifacts=publish_response_artifacts,
            persist_proxy_request_log=persist_proxy_request_log,
            log_rag_error_private=log_rag_error_private,
            rag_request_completed_payload=rag_request_completed_payload,
        )
    )
