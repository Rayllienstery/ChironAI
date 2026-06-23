"""Post-stream helpers for chat completion SSE orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm_proxy.chat_completions_response_helpers import text_parts_from_openai_assistant_message
from llm_proxy.chat_completions_streaming import approx_token_count
from llm_proxy.chat_completions_upstream_budget import _ollama_message_content_str
from llm_proxy.ollama_compat import (
    ollama_message_to_openai_assistant,
    openai_finish_reason_from_ollama,
)

_STREAM_EMPTY_RESPONSE_FALLBACK = "Model returned an empty response. Please retry."


@dataclass(frozen=True)
class NativeStreamToolCallsResolution:
    mapped_calls: list[Any]
    tool_calls_recovered_from_text: bool
    finish_reason: str
    reasoning_content: str
    final_content: str
    full_content: str
    has_tool_calls: bool


@dataclass(frozen=True)
class StreamTraceTokenEstimates:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def resolve_native_stream_tool_calls(
    *,
    tool_calls_raw: list[Any],
    reasoning_content: str,
    final_content: str,
    full_content: str,
    ollama_done_reason: Any,
    budget_exhausted: bool,
    reasoning_guard_triggered: bool,
) -> NativeStreamToolCallsResolution:
    """Map Ollama stream tool_calls; recover from assistant text when missing."""
    mapped_calls: list[Any] = []
    tool_calls_recovered_from_text = False
    reasoning = reasoning_content
    final = final_content
    full = full_content

    if not tool_calls_raw:
        recovery_msg: dict[str, Any] = {"role": "assistant"}
        if reasoning:
            recovery_msg["thinking"] = reasoning
        if final:
            recovery_msg["content"] = final
        elif full and not reasoning:
            recovery_msg["content"] = full
        recovered_msg = ollama_message_to_openai_assistant(recovery_msg)
        recovered_calls = recovered_msg.get("tool_calls")
        if isinstance(recovered_calls, list) and recovered_calls:
            mapped_calls = recovered_calls
            tool_calls_recovered_from_text = True
            recovered_parts = text_parts_from_openai_assistant_message(recovered_msg)
            reasoning = recovered_parts["reasoning_content"]
            final = recovered_parts["final_content"]
            full = recovered_parts["visible_content"]

    has_tool_calls = bool(tool_calls_raw or mapped_calls)
    if has_tool_calls:
        fake_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls_raw}
        if tool_calls_raw and full:
            fake_msg["content"] = full
        if tool_calls_raw:
            openai_mapped = ollama_message_to_openai_assistant(fake_msg)
            mapped_calls = openai_mapped.get("tool_calls") or []
        finish_reason = "tool_calls"
    else:
        finish_reason = resolve_stream_finish_reason(
            ollama_done_reason=ollama_done_reason,
            budget_exhausted=budget_exhausted,
            reasoning_guard_triggered=reasoning_guard_triggered,
        )

    return NativeStreamToolCallsResolution(
        mapped_calls=mapped_calls,
        tool_calls_recovered_from_text=tool_calls_recovered_from_text,
        finish_reason=finish_reason,
        reasoning_content=reasoning,
        final_content=final,
        full_content=full,
        has_tool_calls=has_tool_calls,
    )


def resolve_stream_finish_reason(
    *,
    ollama_done_reason: Any,
    budget_exhausted: bool,
    reasoning_guard_triggered: bool,
) -> str:
    finish_reason = openai_finish_reason_from_ollama({}, ollama_done_reason=ollama_done_reason)
    if budget_exhausted or reasoning_guard_triggered:
        return "length"
    return finish_reason


def estimate_prompt_tokens_from_ollama_messages(messages: list[Any]) -> int:
    prompt_text = " ".join(
        _ollama_message_content_str(m.get("content"))
        for m in messages
        if isinstance(m, dict)
    )
    return approx_token_count(prompt_text)


def estimate_prompt_tokens_from_messages_json(messages: list[Any]) -> int:
    return max(1, int(len(json.dumps(messages, ensure_ascii=False)) / 4))


def apply_stream_empty_response_fallback(
    full_response: str,
    final_content: str,
) -> tuple[str, str, bool]:
    """Return updated visible/final text and whether the fallback was applied."""
    if full_response.strip():
        return full_response, final_content, False
    return _STREAM_EMPTY_RESPONSE_FALLBACK, _STREAM_EMPTY_RESPONSE_FALLBACK, True


def build_stream_trace_token_estimates(
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> StreamTraceTokenEstimates:
    return StreamTraceTokenEstimates(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def build_ollama_stream_token_estimates_dict(estimates: StreamTraceTokenEstimates) -> dict[str, int]:
    return {
        "prompt_tokens_estimated": estimates.prompt_tokens,
        "completion_tokens_estimated": estimates.completion_tokens,
        "total_tokens_estimated": estimates.total_tokens,
    }


def build_native_tools_stream_response_base(
    *,
    stream_latency_ms: int,
    mapped_calls_count: int,
    tool_calls_raw_count: int,
    reasoning_guard_triggered: bool,
    ollama_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "latency_ms": stream_latency_ms,
        "tool_calls_count": mapped_calls_count if mapped_calls_count else tool_calls_raw_count,
        "native_tools": True,
        "reasoning_only_guard_triggered": bool(reasoning_guard_triggered),
        **ollama_metrics,
    }


def build_standard_stream_response_base(
    *,
    stream_latency_ms: int,
    reasoning_guard_triggered: bool,
    ollama_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "latency_ms": stream_latency_ms,
        "reasoning_only_guard_triggered": bool(reasoning_guard_triggered),
        **ollama_metrics,
    }


def build_provider_stream_step(
    *,
    name: str,
    duration_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, int | str]:
    return {
        "name": name,
        "duration_ms": duration_ms,
        "tokens_in_est": prompt_tokens,
        "tokens_out_est": completion_tokens,
    }


def native_tools_stream_trace_response_extras(
    *,
    gemini_upserted: int,
    tool_calls_raw: list[Any],
    mapped_calls: list[Any],
    tool_calls_recovered_from_text: bool,
) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    if gemini_upserted:
        extras["gemini_tool_state_upserted_count"] = int(gemini_upserted)
    if tool_calls_raw:
        extras["tool_calls_raw"] = tool_calls_raw
    if mapped_calls:
        extras["tool_calls"] = mapped_calls
    if tool_calls_recovered_from_text:
        extras["tool_calls_recovered_from_text"] = True
    return extras
