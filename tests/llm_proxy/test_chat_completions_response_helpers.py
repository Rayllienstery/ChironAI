from __future__ import annotations

from llm_proxy.chat_completions_response_helpers import (
    final_or_compat_content,
    proxy_settings_optional_int,
    reasoning_sse_delta,
    stream_reasoning_guard_message,
    text_parts_from_openai_assistant_message,
    tool_loop_limit_final_message,
    upstream_chat_error_message,
    with_initial_system_message,
)


class _Response:
    status_code = 503
    reason = "Service Unavailable"
    url = "http://localhost:11434/api/chat"


class _HttpError(Exception):
    response = _Response()


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


def test_upstream_chat_error_message_wraps_http_status_and_budget_hint() -> None:
    msg = upstream_chat_error_message(
        _HttpError("503 Server Error"),
        {
            "request": {
                "upstream_context_compaction": {"still_over_budget_after_tool_trim": True},
                "input_budget": {"input_budget_tokens": 110592},
                "tools_count_effective": 54,
            }
        },
        model="minimax-m3:cloud",
    )

    assert msg.startswith("[Error: upstream Ollama returned 503 Service Unavailable")
    assert "http://localhost:11434/api/chat" in msg
    assert "model minimax-m3:cloud" in msg
    assert "still over budget after compaction" in msg
    assert "54 tools" in msg


def test_upstream_chat_error_message_handles_plain_exception() -> None:
    msg = upstream_chat_error_message(RuntimeError("boom"), {}, model="tiny")

    assert msg == "[Error: upstream Ollama request failed: boom while calling model tiny.]"


def test_upstream_chat_error_message_compacts_serialized_ollama_error() -> None:
    raw = (
        "upstream Ollama request failed: {'response': {'_content': "
        "'b\\'{\"error\":\"model \\\\\\'High-worker\\\\\\' not found\"}\\'', "
        "'status_code': 404, 'headers': {'_store': {'content-type': "
        "['Content-Type', 'application/json; charset=utf-8']}}, 'cookies': "
        f"{{'_policy': '{'x' * 2000}'}}"
    )

    msg = upstream_chat_error_message(RuntimeError(raw), {}, model="High-worker")

    assert msg == (
        "[Error: upstream Ollama returned 404: model 'High-worker' not found "
        "while calling model High-worker.]"
    )
    assert len(msg) < 140


def test_upstream_chat_error_message_wraps_response_none_with_payload_diagnostics() -> None:
    raw = (
        "upstream Ollama request failed: {'response': None, 'request': {'method': 'POST', "
        "'url': 'http://localhost:11434/api/chat', 'headers': {'_store': {'content-length': "
        "['Content-Length', '499741'], 'content-type': ['Content-Type', 'application/json']}}}}"
    )

    msg = upstream_chat_error_message(
        RuntimeError(raw),
        {
            "ollama": {
                "messages": [
                    {"role": "system", "content_length_chars": 1184},
                    {"role": "tool", "content_length_chars": 28200},
                ]
            }
        },
        model="kimi-k2.7-code:cloud",
    )

    assert "failed before receiving an HTTP response" in msg
    assert "499741-byte request payload" in msg
    assert "29384 message content chars" in msg
    assert "large upstream context/tools are a strong suspect" in msg
    assert "while calling model kimi-k2.7-code:cloud" in msg


def test_upstream_chat_error_message_explains_extension_worker_timeout() -> None:
    msg = upstream_chat_error_message(
        RuntimeError("worker call timed out: request 8"),
        {},
        model="kimi-k2.7-code:cloud",
    )

    assert "Ollama provider extension worker timed out" in msg
    assert "sandbox request 8" in msg
    assert "restart the ollama-provider worker from Extensions" in msg
    assert "while calling model kimi-k2.7-code:cloud" in msg
