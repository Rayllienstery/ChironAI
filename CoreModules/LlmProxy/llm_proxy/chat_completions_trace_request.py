"""Initial ``trace['request']`` payload for chat completions."""

from __future__ import annotations

from typing import Any

from llm_proxy.tool_helpers import _extract_tool_name

_PROXY_TRACE_META_KEYS = frozenset(
    {
        "proxy_v1_route",
        "responses_client_stream",
        "incoming_request_id",
        "responses_previous_response_id",
    }
)


def build_chat_trace_request_dict(
    *,
    requested_model: str,
    actual_model: str,
    stream: bool,
    build_sse_streaming: bool,
    chat_max_tokens: int | None,
    effective_num_predict: int | None,
    effective_num_ctx: int | None,
    include_rag_metadata: bool,
    tools: list[Any],
    selected_edit_tool_name: str | None,
    selected_edit_tool: dict[str, Any] | None,
    tool_choice: Any,
    tool_choice_effective: Any,
    has_tool_result: bool,
    tool_result_indicates_failure: bool,
    post_tool_success_turn: bool,
    last_tool_content: str,
    force_rag: bool,
    fetch_web_knowledge: bool,
    fetch_web_knowledge_source: str,
    explicit_reasoning: Any,
    reasoning_level: Any,
    reasoning_for_prompt: Any,
    user_query: str,
    is_autocomplete: bool,
    testing_disable_rerank: bool,
    client_request_id: Any,
) -> dict[str, Any]:
    """Build the base ``trace['request']`` dict before RAG/model-specific fields."""
    return {
        "requested_model": requested_model,
        "actual_model": actual_model,
        "proxy_pipeline": "passthrough_only",
        "stream": bool(stream),
        "build_sse_streaming": build_sse_streaming,
        "max_tokens": chat_max_tokens,
        "effective_num_predict": effective_num_predict,
        "effective_num_ctx": effective_num_ctx,
        "ollama_chat_stream": False,
        "include_rag_metadata": bool(include_rag_metadata),
        "tools_count": len(tools),
        "tools_names_preview": [n for n in (_extract_tool_name(t) for t in tools) if n][:20],
        "selected_edit_tool_name": selected_edit_tool_name,
        "selected_edit_tool_required": (
            (
                ((selected_edit_tool or {}).get("function") or {}).get("parameters") or {}
            ).get("required")
            if isinstance(selected_edit_tool, dict)
            else None
        ),
        "tool_choice": tool_choice if isinstance(tool_choice, (str, dict)) else None,
        "tool_choice_effective": tool_choice_effective
        if isinstance(tool_choice_effective, (str, dict))
        else str(tool_choice_effective),
        "has_tool_result": bool(has_tool_result),
        "tool_result_indicates_failure": bool(tool_result_indicates_failure),
        "post_tool_success_turn": bool(post_tool_success_turn),
        "tool_result_last_content_preview": (last_tool_content[:240] if last_tool_content else ""),
        "force_rag": bool(force_rag),
        "fetch_web_knowledge": bool(fetch_web_knowledge),
        "fetch_web_knowledge_source": fetch_web_knowledge_source,
        "reasoning_level": explicit_reasoning or reasoning_level,
        "reasoning_for_prompt": reasoning_for_prompt,
        "user_query_preview": (user_query or "")[:500],
        "is_autocomplete": bool(is_autocomplete),
        "testing_disable_rerank": bool(testing_disable_rerank),
        "client_request_id": str(client_request_id or "").strip() or None,
    }


def enrich_chat_trace_request(
    trace: dict[str, Any],
    *,
    input_budget: dict[str, Any] | None,
    effective_max_agent_steps: int | None,
    tool_loop_limit_reached: bool,
    trace_chain_id: str | None,
    trace_chain_source: str | None,
    tool_loop_stats: dict[str, Any] | None,
    proxy_trace_meta: dict[str, Any] | None,
    body: dict[str, Any],
    append_trace_warning: Any,
) -> None:
    """Attach optional request trace fields after the base dict is stored."""
    request = trace.setdefault("request", {})
    if input_budget is not None:
        request["input_budget"] = dict(input_budget)
    if effective_max_agent_steps is not None:
        request["effective_max_agent_steps"] = effective_max_agent_steps
    if tool_loop_limit_reached:
        request["tool_loop_limit_reached"] = True
        request["tools_suppressed_for_step_limit"] = True
        append_trace_warning(trace, "tool_loop_limit_reached")
    if trace_chain_id:
        request["trace_chain_id"] = trace_chain_id
        request["trace_chain_source"] = trace_chain_source
    if tool_loop_stats is not None:
        request["tool_loop_stats"] = tool_loop_stats
    if proxy_trace_meta:
        for key, value in proxy_trace_meta.items():
            if key in _PROXY_TRACE_META_KEYS:
                request[key] = value
    if body.get("tools_count_raw") is not None:
        request["tools_count_raw"] = body.get("tools_count_raw")
    if body.get("tools_count_normalized") is not None:
        request["tools_count_normalized"] = body.get("tools_count_normalized")
    if isinstance(body.get("tools_types_raw"), list):
        request["tools_types_raw"] = body.get("tools_types_raw")
    if isinstance(body.get("tools_types_dropped"), list):
        request["tools_types_dropped"] = body.get("tools_types_dropped")
    if isinstance(body.get("tools_types_normalized"), list):
        request["tools_types_normalized"] = body.get("tools_types_normalized")
    if body.get("tool_choice_raw") is not None:
        request["tool_choice_raw"] = body.get("tool_choice_raw")
    if body.get("tool_choice_normalized") is not None:
        request["tool_choice_normalized"] = body.get("tool_choice_normalized")
