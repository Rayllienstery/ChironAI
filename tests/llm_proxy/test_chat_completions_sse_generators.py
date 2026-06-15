from __future__ import annotations

from typing import Any

from llm_proxy.chat_completions_sse_generators import (
    LegacyPlainTextStreamContext,
    LegacyToolCallStreamContext,
    NativeToolsSingleStreamContext,
    PlainSingleStreamContext,
    ToolLimitStreamContext,
    iter_legacy_plain_text_sse_stream,
    iter_legacy_tool_call_sse_stream,
    iter_native_tools_single_sse_stream,
    iter_plain_single_sse_stream,
    iter_tool_limit_sse_stream,
)


class _RecordingPersistLog:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> None:
        self.calls.append(dict(kwargs))


def test_iter_tool_limit_sse_stream_yields_and_persists() -> None:
    persist = _RecordingPersistLog()
    chunks = list(
        iter_tool_limit_sse_stream(
            ToolLimitStreamContext(
                response_id="chatcmpl-test",
                client_visible_model="test-model",
                content="limit reached",
                private_build=False,
                user_query="hello world",
                log_preview=50,
                latency_ms=12,
                trace={"trace_id": "t1"},
                prompt_tokens_approx=3,
                completion_tokens_approx=4,
                total_tokens_approx=7,
                persist_proxy_request_log=persist,
            )
        )
    )
    assert any("limit reached" in chunk for chunk in chunks)
    assert len(persist.calls) == 1
    assert persist.calls[0]["extra_metadata"] == {"tool_loop_limit_response": True}


def test_iter_tool_limit_sse_stream_skips_persist_for_private_build() -> None:
    persist = _RecordingPersistLog()
    list(
        iter_tool_limit_sse_stream(
            ToolLimitStreamContext(
                response_id="chatcmpl-test",
                client_visible_model="test-model",
                content="limit reached",
                private_build=True,
                user_query="hello",
                log_preview=50,
                latency_ms=12,
                trace={"trace_id": "t1"},
                prompt_tokens_approx=3,
                completion_tokens_approx=4,
                total_tokens_approx=7,
                persist_proxy_request_log=persist,
            )
        )
    )
    assert persist.calls == []


def test_iter_legacy_tool_call_sse_stream_emits_tool_calls() -> None:
    tool_call = {
        "id": "call_abc",
        "type": "function",
        "function": {"name": "edit_file", "arguments": '{"path":"a.py"}'},
    }
    chunks = list(
        iter_legacy_tool_call_sse_stream(
            LegacyToolCallStreamContext(
                client_visible_model="test-model",
                tool_call=tool_call,
                selected_edit_tool_name="edit_file",
            )
        )
    )
    joined = "".join(chunks)
    assert "tool_calls" in joined
    assert "edit_file" in joined
    assert "call_abc" in joined


def test_iter_legacy_plain_text_sse_stream_emits_content() -> None:
    chunks = list(
        iter_legacy_plain_text_sse_stream(
            LegacyPlainTextStreamContext(
                client_visible_model="test-model",
                tool_plain_fallback="fallback text",
            )
        )
    )
    assert any("fallback text" in chunk for chunk in chunks)


def test_iter_plain_single_sse_stream_persists_log() -> None:
    persist = _RecordingPersistLog()
    chunks = list(
        iter_plain_single_sse_stream(
            PlainSingleStreamContext(
                response_id="chatcmpl-single",
                client_visible_model="test-model",
                content="answer",
                content_parts={"reasoning_content": "think"},
                tool_calls=[],
                finish_reason="stop",
                include_reasoning_content=True,
                private_build=False,
                user_query="q",
                content_preview="answer",
                latency_ms=20,
                trace={"trace_id": "t2"},
                prompt_tokens_approx=1,
                completion_tokens_approx=2,
                total_tokens_approx=3,
                persist_proxy_request_log=persist,
            )
        )
    )
    assert any("answer" in chunk for chunk in chunks)
    assert len(persist.calls) == 1
    assert persist.calls[0]["sse_single_chunk"] is True


class _RecordingWiring:
    status_idle = "idle"

    def __init__(self) -> None:
        self.proxy_status: str | None = None
        self.latest_seconds: float | None = None
        self.latest_tokens: int | None = None

    def set_proxy_status(self, status: str) -> None:
        self.proxy_status = status

    def set_latest_request_seconds(self, value: float) -> None:
        self.latest_seconds = value

    def set_latest_request_total_tokens(self, value: int) -> None:
        self.latest_tokens = value


def test_iter_native_tools_single_sse_stream_updates_trace_and_wiring() -> None:
    w = _RecordingWiring()
    trace: dict[str, Any] = {"ollama": {}, "steps": []}
    artifacts: list[dict[str, str]] = []
    persist = _RecordingPersistLog()

    def publish_trace(tr: dict[str, Any]) -> None:
        trace.update(tr)

    def publish_response_artifacts(**kwargs: str) -> None:
        artifacts.append(dict(kwargs))

    list(
        iter_native_tools_single_sse_stream(
            NativeToolsSingleStreamContext(
                w=w,  # type: ignore[arg-type]
                trace=trace,
                private_build=False,
                client_visible_model="test-model",
                content_str="done",
                content_parts={
                    "visible_content": "done",
                    "reasoning_content": "",
                    "final_content": "done",
                },
                tool_calls_out=[],
                finish="stop",
                include_reasoning_content=False,
                user_query="hello",
                latency_ms=30,
                prompt_tokens=5,
                completion_tokens=6,
                start_time=0.0,
                publish_trace=publish_trace,
                publish_response_artifacts=publish_response_artifacts,
                persist_proxy_request_log=persist,
            )
        )
    )

    assert trace["ollama"]["chat_stream"] is False
    assert trace["steps"][-1]["name"] == "provider_chat_native_tools_sse_single"
    assert artifacts[0]["visible_content"] == "done"
    assert w.proxy_status == w.status_idle
    assert w.latest_tokens == 11
    assert len(persist.calls) == 1
