from __future__ import annotations

import json
from typing import Any

from llm_proxy.chat_completions_streaming import (
    StreamContentAccumulator,
    iter_sse_from_ollama_stream_events,
    iter_sse_plain_content_response,
    iter_sse_single_shot_assistant,
    iter_sse_tool_limit_response,
    openai_chat_completion_chunk,
    sse_finish_chunk,
    stream_completion_id,
)


def _parse_sse_data(line: str) -> dict[str, Any]:
    assert line.startswith("data: ")
    return json.loads(line[6:].strip())


def test_openai_chat_completion_chunk_shape() -> None:
    line = openai_chat_completion_chunk(
        "id-1",
        "m",
        delta={"content": "hi"},
        finish_reason=None,
    )
    payload = _parse_sse_data(line)
    assert payload["object"] == "chat.completion.chunk"
    assert payload["choices"][0]["delta"] == {"content": "hi"}
    assert payload["choices"][0]["finish_reason"] is None


def test_iter_sse_tool_limit_response_order() -> None:
    lines = list(iter_sse_tool_limit_response("id-1", "m", "limit msg"))
    assert len(lines) == 4
    assert _parse_sse_data(lines[0])["choices"][0]["delta"] == {"role": "assistant"}
    assert _parse_sse_data(lines[1])["choices"][0]["delta"] == {"content": "limit msg"}
    assert _parse_sse_data(lines[2])["choices"][0]["finish_reason"] == "stop"
    assert lines[3] == "data: [DONE]\n\n"


def test_iter_sse_from_ollama_stream_events_content_and_done() -> None:
    acc = StreamContentAccumulator()
    events = iter(
        [
            ("content_delta", "hello"),
            ("done", {"done_reason": "stop"}),
        ]
    )
    lines = list(
        iter_sse_from_ollama_stream_events(
            events,
            completion_id="cid",
            client_visible_model="model",
            include_reasoning_content=False,
            accumulator=acc,
            reasoning_guard_limit_chars=50_000,
        )
    )
    assert acc.visible_content == "hello"
    assert acc.ollama_done_reason == "stop"
    assert len(lines) == 1
    assert _parse_sse_data(lines[0])["choices"][0]["delta"] == {"content": "hello"}


def test_iter_sse_from_ollama_stream_events_reasoning_guard_stops() -> None:
    acc = StreamContentAccumulator()
    long_reasoning = "x" * 100
    events = iter([("thinking_delta", long_reasoning)])
    guard_calls: list[str] = []

    lines = list(
        iter_sse_from_ollama_stream_events(
            events,
            completion_id="cid",
            client_visible_model="model",
            include_reasoning_content=False,
            accumulator=acc,
            reasoning_guard_limit_chars=50,
            on_reasoning_guard=lambda: guard_calls.append("guard"),
        )
    )
    assert acc.reasoning_guard_triggered is True
    assert guard_calls == ["guard"]
    assert len(lines) == 2
    assert "Error: reasoning-only" in _parse_sse_data(lines[1])["choices"][0]["delta"]["content"]


def test_iter_sse_single_shot_includes_tool_calls() -> None:
    lines = list(
        iter_sse_single_shot_assistant(
            stream_completion_id(),
            "m",
            content="",
            reasoning_content="",
            tool_calls_payload=[{"index": 0, "id": "c1", "type": "function", "function": {"name": "edit"}}],
            finish_reason="tool_calls",
            include_reasoning_content=True,
        )
    )
    assert _parse_sse_data(lines[-2])["choices"][0]["finish_reason"] == "tool_calls"
    assert "tool_calls" in _parse_sse_data(lines[-3])["choices"][0]["delta"]


def test_sse_finish_chunk_format() -> None:
    line = sse_finish_chunk("id-1", "m", "length")
    assert _parse_sse_data(line)["choices"][0]["finish_reason"] == "length"
