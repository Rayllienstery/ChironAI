from __future__ import annotations

from llm_proxy.chat_completions_streaming_orchestration import (
    apply_standard_stream_budget_to_content,
    apply_stream_empty_response_fallback,
    build_native_tools_stream_response_base,
    build_ollama_stream_token_estimates_dict,
    build_provider_stream_step,
    build_stream_trace_token_estimates,
    estimate_prompt_tokens_from_messages_json,
    estimate_prompt_tokens_from_ollama_messages,
    resolve_native_stream_tool_calls,
    resolve_stream_finish_reason,
)


def test_resolve_stream_finish_reason_length_on_budget_or_guard() -> None:
    assert resolve_stream_finish_reason(
        ollama_done_reason="stop",
        budget_error="",
        reasoning_guard_triggered=False,
    ) == "stop"
    assert resolve_stream_finish_reason(
        ollama_done_reason="stop",
        budget_error="out of tokens",
        reasoning_guard_triggered=False,
    ) == "length"
    assert resolve_stream_finish_reason(
        ollama_done_reason="stop",
        budget_error="",
        reasoning_guard_triggered=True,
    ) == "length"


def test_apply_stream_empty_response_fallback() -> None:
    full, final, applied = apply_stream_empty_response_fallback("hello", "hello")
    assert applied is False
    assert full == "hello"

    full, final, applied = apply_stream_empty_response_fallback("  ", "")
    assert applied is True
    assert "empty response" in full.lower()
    assert full == final


def test_estimate_prompt_tokens_from_ollama_messages() -> None:
    messages = [{"role": "user", "content": "abcd" * 4}]
    assert estimate_prompt_tokens_from_ollama_messages(messages) >= 1


def test_estimate_prompt_tokens_from_messages_json() -> None:
    messages = [{"role": "user", "content": "x" * 40}]
    assert estimate_prompt_tokens_from_messages_json(messages) >= 10


def test_build_stream_trace_token_estimates() -> None:
    estimates = build_stream_trace_token_estimates(prompt_tokens=5, completion_tokens=7)
    assert estimates.total_tokens == 12
    payload = build_ollama_stream_token_estimates_dict(estimates)
    assert payload["total_tokens_estimated"] == 12


def test_build_native_tools_stream_response_base() -> None:
    payload = build_native_tools_stream_response_base(
        stream_latency_ms=100,
        mapped_calls_count=2,
        tool_calls_raw_count=0,
        reasoning_guard_triggered=True,
        ollama_metrics={"eval_count": 3},
    )
    assert payload["native_tools"] is True
    assert payload["tool_calls_count"] == 2
    assert payload["reasoning_only_guard_triggered"] is True
    assert payload["eval_count"] == 3


def test_resolve_native_stream_tool_calls_no_tools_stop_finish() -> None:
    result = resolve_native_stream_tool_calls(
        tool_calls_raw=[],
        reasoning_content="",
        final_content="hello",
        full_content="hello",
        ollama_done_reason="stop",
        budget_error="",
        reasoning_guard_triggered=False,
    )
    assert not result.has_tool_calls
    assert result.finish_reason == "stop"
    assert result.full_content == "hello"


def test_resolve_native_stream_tool_calls_length_on_guard() -> None:
    result = resolve_native_stream_tool_calls(
        tool_calls_raw=[],
        reasoning_content="thinking",
        final_content="",
        full_content="thinking",
        ollama_done_reason="stop",
        budget_error="",
        reasoning_guard_triggered=True,
    )
    assert result.finish_reason == "length"


def test_apply_standard_stream_budget_to_content() -> None:
    full, final = apply_standard_stream_budget_to_content("hi", "hi", "")
    assert full == "hi"
    full, final = apply_standard_stream_budget_to_content("", "", "budget hit")
    assert full == "budget hit"
    assert final == "budget hit"


def test_build_provider_stream_step() -> None:
    step = build_provider_stream_step(
        name="provider_chat_stream",
        duration_ms=50,
        prompt_tokens=10,
        completion_tokens=20,
    )
    assert step["name"] == "provider_chat_stream"
    assert step["tokens_in_est"] == 10
