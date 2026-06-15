from __future__ import annotations

from llm_proxy.chat_completions_native_tools_prep import (
    analyze_tool_result_failure,
    analyze_tool_turn_state,
    compute_post_tool_success_turn,
    last_tool_message_content,
    messages_have_tool_result,
    resolve_native_tools_policy,
)


def test_messages_have_tool_result() -> None:
    assert not messages_have_tool_result([{"role": "user", "content": "hi"}])
    assert messages_have_tool_result(
        [{"role": "user", "content": "hi"}, {"role": "tool", "content": "ok"}]
    )


def test_last_tool_message_content_prefers_latest_tool() -> None:
    messages = [
        {"role": "tool", "content": "old"},
        {"role": "user", "content": "again"},
        {"role": "tool", "output": "new"},
    ]
    assert last_tool_message_content(messages) == "new"


def test_analyze_tool_result_failure_detects_phrases_and_json() -> None:
    assert analyze_tool_result_failure("path not found: foo.swift")
    assert analyze_tool_result_failure('{"ok": false, "error": "boom"}')
    assert analyze_tool_result_failure('{"metadata": {"exit_code": 1}}')
    assert not analyze_tool_result_failure('{"ok": true, "content": "done"}')


def test_compute_post_tool_success_turn_requires_latest_tool_without_newer_user() -> None:
    messages = [
        {"role": "user", "content": "edit"},
        {"role": "tool", "content": "done"},
    ]
    assert compute_post_tool_success_turn(
        messages,
        has_tool_result=True,
        tool_result_indicates_failure=False,
    )
    messages_with_user_after_tool = [
        {"role": "tool", "content": "done"},
        {"role": "user", "content": "thanks"},
    ]
    assert not compute_post_tool_success_turn(
        messages_with_user_after_tool,
        has_tool_result=True,
        tool_result_indicates_failure=False,
    )


def test_analyze_tool_turn_state_composes_helpers() -> None:
    messages = [{"role": "user", "content": "x"}, {"role": "tool", "content": "ok"}]
    has_tool, content, failed, post_success = analyze_tool_turn_state(messages)
    assert has_tool
    assert content == "ok"
    assert not failed
    assert post_success


def test_resolve_native_tools_policy_suppresses_at_step_limit() -> None:
    messages = [{"role": "user", "content": "go"}]
    for _ in range(5):
        messages.append({"role": "assistant", "tool_calls": [{"id": "1", "type": "function"}]})
        messages.append({"role": "tool", "content": "ok"})
    tools = [{"type": "function", "function": {"name": "read", "parameters": {}}}]
    policy = resolve_native_tools_policy(
        messages,
        tools,
        "auto",
        effective_max_agent_steps=3,
    )
    assert policy.tool_loop_limit_reached
    assert policy.tools == []
    assert policy.tool_choice_effective == "none"
    assert not policy.use_native_tools
