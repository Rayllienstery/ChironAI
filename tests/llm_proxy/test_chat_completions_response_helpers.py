from __future__ import annotations

from llm_proxy.chat_completions_response_helpers import (
    final_or_compat_content,
    proxy_settings_optional_int,
    reasoning_sse_delta,
    stream_reasoning_guard_message,
    text_parts_from_openai_assistant_message,
    tool_loop_limit_final_message,
    with_initial_system_message,
)


def test_reasoning_sse_delta_maps_thinking_to_reasoning_content() -> None:
    assert reasoning_sse_delta("thinking_delta", "x", include_reasoning_content=False) == {
        "reasoning_content": "x"
    }
    assert reasoning_sse_delta("thinking_delta", "x", include_reasoning_content=True) == {"content": "x"}


def test_stream_reasoning_guard_message_triggers_on_long_reasoning_only() -> None:
    assert stream_reasoning_guard_message(
        reasoning_text="a" * 100,
        final_text="",
        tool_calls_count=0,
        limit_chars=50,
    ).startswith("[Error: reasoning-only response guard")


def test_with_initial_system_message_prepends_or_merges() -> None:
    merged = with_initial_system_message([{"role": "system", "content": "A"}], "B")
    assert merged[0]["content"] == "A\n\nB"
    prepended = with_initial_system_message([{"role": "user", "content": "hi"}], "sys")
    assert prepended[0] == {"role": "system", "content": "sys"}


def test_text_parts_from_openai_assistant_message() -> None:
    parts = text_parts_from_openai_assistant_message(
        {"reasoning_content": "think", "content": "answer"}
    )
    assert parts["visible_content"] == "think\n\nanswer"
    assert parts["final_content"] == "answer"


def test_final_or_compat_content_selects_field() -> None:
    parts = {"visible_content": "both", "final_content": "final"}
    assert final_or_compat_content(parts, include_reasoning_content=True) == "both"
    assert final_or_compat_content(parts, include_reasoning_content=False) == "final"


def test_proxy_settings_optional_int_bounds() -> None:
    assert proxy_settings_optional_int({"k": 10}, "k", 1, 100) == 10
    assert proxy_settings_optional_int({"k": 0}, "k", 1, 100) is None
    assert proxy_settings_optional_int({"k": "bad"}, "k", 1, 100) is None


def test_tool_loop_limit_final_message() -> None:
    msg = tool_loop_limit_final_message(
        {
            "request": {
                "tool_loop_limit_reached": True,
                "tool_loop_stats": {"rounds": 3, "dominant_tool": "apply_edit"},
            }
        }
    )
    assert "max_agent_steps limit reached" in msg
    assert "apply_edit" in msg
