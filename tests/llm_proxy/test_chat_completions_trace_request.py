from __future__ import annotations

from llm_proxy.chat_completions_trace_request import (
    build_chat_trace_request_dict,
    enrich_chat_trace_request,
)


def test_build_chat_trace_request_dict_core_fields() -> None:
    payload = build_chat_trace_request_dict(
        requested_model="build-1",
        actual_model="llama3",
        stream=True,
        build_sse_streaming=True,
        chat_max_tokens=512,
        effective_num_predict=256,
        effective_num_ctx=8192,
        include_rag_metadata=False,
        tools=[{"type": "function", "function": {"name": "edit_file"}}],
        selected_edit_tool_name="edit_file",
        selected_edit_tool={"function": {"parameters": {"required": ["path"]}}},
        tool_choice="auto",
        tool_choice_effective="auto",
        has_tool_result=False,
        tool_result_indicates_failure=False,
        post_tool_success_turn=False,
        last_tool_content="",
        force_rag=False,
        fetch_web_knowledge=True,
        fetch_web_knowledge_source="proxy_settings",
        explicit_reasoning=None,
        reasoning_level="medium",
        reasoning_for_prompt="medium",
        user_query="hello",
        is_autocomplete=False,
        testing_disable_rerank=False,
        client_request_id="req-1",
    )
    assert payload["requested_model"] == "build-1"
    assert payload["stream"] is True
    assert payload["tools_count"] == 1
    assert payload["tools_names_preview"] == ["edit_file"]
    assert payload["selected_edit_tool_required"] == ["path"]
    assert payload["client_request_id"] == "req-1"


def test_enrich_chat_trace_request_optional_fields() -> None:
    trace: dict = {"request": {}}
    warnings: list[str] = []

    enrich_chat_trace_request(
        trace,
        input_budget={"input_budget_tokens": 1000},
        effective_max_agent_steps=12,
        tool_loop_limit_reached=True,
        trace_chain_id="chain-1",
        trace_chain_source="client_request_id",
        tool_loop_stats={"rounds": 3},
        proxy_trace_meta={"proxy_v1_route": True, "ignored": "x"},
        body={
            "tools_count_raw": 2,
            "tool_choice_raw": "auto",
        },
        append_trace_warning=lambda _trace, code: warnings.append(code),
    )
    request = trace["request"]
    assert request["input_budget"]["input_budget_tokens"] == 1000
    assert request["effective_max_agent_steps"] == 12
    assert request["tool_loop_limit_reached"] is True
    assert request["trace_chain_id"] == "chain-1"
    assert request["tool_loop_stats"] == {"rounds": 3}
    assert request["proxy_v1_route"] is True
    assert "ignored" not in request
    assert request["tools_count_raw"] == 2
    assert warnings == ["tool_loop_limit_reached"]
