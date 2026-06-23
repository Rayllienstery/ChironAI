from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root not in sys.path:
    sys.path.insert(0, root)


@pytest.fixture(autouse=True)
def _workspace_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm_proxy.workspace._workspace_root_fn", lambda: Path(root))


from llm_proxy.chat_completions_legacy_tool_stream import (
    LegacyToolStreamContext,
    compact_messages_for_chat_retry,
    is_legacy_tool_stream_mode,
    resolve_legacy_tool_stream_edit,
    try_build_legacy_tool_stream_response,
)


def test_is_legacy_tool_stream_mode_requires_stream_tools_and_pre_tool_turn() -> None:
    assert is_legacy_tool_stream_mode(
        stream=True,
        tools=[{"type": "function"}],
        tool_choice_effective="auto",
        post_tool_success_turn=False,
    )
    assert not is_legacy_tool_stream_mode(
        stream=False,
        tools=[{"type": "function"}],
        tool_choice_effective="auto",
        post_tool_success_turn=False,
    )
    assert not is_legacy_tool_stream_mode(
        stream=True,
        tools=[],
        tool_choice_effective="auto",
        post_tool_success_turn=False,
    )
    assert not is_legacy_tool_stream_mode(
        stream=True,
        tools=[{"type": "function"}],
        tool_choice_effective="none",
        post_tool_success_turn=False,
    )
    assert not is_legacy_tool_stream_mode(
        stream=True,
        tools=[{"type": "function"}],
        tool_choice_effective="auto",
        post_tool_success_turn=True,
    )


def test_compact_messages_for_chat_retry_keeps_system_and_last_user() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "mid"},
        {"role": "user", "content": "last"},
    ]
    compact = compact_messages_for_chat_retry(messages)
    assert compact == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "last"},
    ]


def test_compact_messages_for_chat_retry_empty_input() -> None:
    assert compact_messages_for_chat_retry([]) == []


_EDIT_TOOL = {
    "function": {
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
}


def test_resolve_legacy_tool_stream_edit_builds_tool_call_from_json() -> None:
    content = (
        '{"file_path":"src/App.jsx","mode":"edit","new_text":"const tabs = [];",'
        '"range":{"start_line":1,"start_col":1,"end_line":1,"end_col":1}}'
    )
    result = resolve_legacy_tool_stream_edit(
        streamed_content=content,
        stream_tool_error=None,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        user_query="edit App.jsx",
    )
    assert result.tool_call is not None
    assert result.tool_call["function"]["name"] == "edit_file"
    assert result.edit_payload is not None


def test_resolve_legacy_tool_stream_edit_plain_text_when_no_json() -> None:
    result = resolve_legacy_tool_stream_edit(
        streamed_content="Normal assistant answer without JSON.",
        stream_tool_error=None,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        user_query="edit",
    )
    assert result.tool_call is None
    assert result.tool_plain_fallback == "Normal assistant answer without JSON."


def test_resolve_legacy_tool_stream_edit_whitespace_body_skips_tool_call() -> None:
    content = (
        '{"file_path":"src/App.jsx","mode":"edit","new_text":"  \\n\\t  "}'
    )
    result = resolve_legacy_tool_stream_edit(
        streamed_content=content,
        stream_tool_error=None,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        user_query="edit App.jsx",
    )
    assert result.tool_call is None
    assert "non-empty edit body" in result.tool_plain_fallback


def test_resolve_legacy_tool_stream_edit_empty_response_message() -> None:
    result = resolve_legacy_tool_stream_edit(
        streamed_content="   ",
        stream_tool_error=None,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        user_query="edit",
    )
    assert result.tool_call is None
    assert "empty response" in result.tool_plain_fallback.lower()


def test_resolve_legacy_tool_stream_edit_skips_on_upstream_error() -> None:
    result = resolve_legacy_tool_stream_edit(
        streamed_content="",
        stream_tool_error="upstream failed",
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        user_query="edit",
    )
    assert result.tool_call is None
    assert result.tool_plain_fallback == ""


class _FakeWiring:
    status_response = "responding"
    status_idle = "idle"

    def __init__(self) -> None:
        self.status: str | None = None
        self.latest_seconds: float | None = None

    def set_proxy_status(self, status: str) -> None:
        self.status = status

    def set_latest_request_seconds(self, seconds: float) -> None:
        self.latest_seconds = seconds

    def log_webui_error(self, *_args: Any, **_kwargs: Any) -> None:
        pass


class _FakeChatClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Any]] = []

    def chat(self, messages, _model, stream=False, options=None, think=None):  # noqa: ANN001
        self.calls.append(list(messages))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _minimal_legacy_ctx(
    *,
    chat_client: Any,
    trace: dict[str, Any] | None = None,
    private_build: bool = False,
    persist: Any | None = None,
) -> LegacyToolStreamContext:
    return LegacyToolStreamContext(
        w=_FakeWiring(),
        trace=trace or {"response": {}},
        trace_id="trace-1",
        private_build=private_build,
        client_visible_model="test-model",
        chat_client=chat_client,
        ollama_messages=[
            {"role": "system", "content": "tool json"},
            {"role": "user", "content": "edit"},
        ],
        use_model="ollama-model",
        ollama_think=None,
        user_query="edit file",
        log_preview=80,
        start_time=0.0,
        rag_ctx_for_log=None,
        rag_timings={},
        requested_model="req-model",
        is_autocomplete=False,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=_EDIT_TOOL,
        selected_tool_write_capable=True,
        ollama_options_overlay=lambda: {},
        publish_trace=lambda _tr: None,
        publish_response_artifacts=lambda **_kwargs: None,
        persist_proxy_request_log=persist or (lambda **_kwargs: None),
        log_rag_error_private=lambda *_a, **_k: None,
        rag_request_completed_payload=lambda **_kwargs: {"ok": True},
    )


def test_try_build_legacy_tool_stream_response_returns_plain_sse() -> None:
    client = _FakeChatClient(["Plain answer."])
    response = try_build_legacy_tool_stream_response(_minimal_legacy_ctx(chat_client=client))
    assert response is not None
    body = "".join(response.response)
    assert "Plain answer." in body
    assert '"finish_reason": "stop"' in body


def test_try_build_legacy_tool_stream_response_returns_tool_call_sse() -> None:
    payload = (
        '{"file_path":"src/App.jsx","mode":"edit","new_text":"x",'
        '"range":{"start_line":1,"start_col":1,"end_line":1,"end_col":1}}'
    )
    client = _FakeChatClient([payload])
    persist = MagicMock()
    response = try_build_legacy_tool_stream_response(
        _minimal_legacy_ctx(chat_client=client, persist=persist)
    )
    assert response is not None
    body = "".join(response.response)
    assert '"finish_reason": "tool_calls"' in body
    persist.assert_called_once()
    assert persist.call_args.kwargs["extra_metadata"] == {"stream_tool_mode": "tool_calls"}


def test_try_build_legacy_tool_stream_response_returns_none_on_chat_error() -> None:
    client = _FakeChatClient([RuntimeError("fail"), RuntimeError("retry fail")])
    trace: dict[str, Any] = {"response": {}}
    response = try_build_legacy_tool_stream_response(
        _minimal_legacy_ctx(chat_client=client, trace=trace)
    )
    assert response is None
    assert trace["response"]["tool_mode_error"] == "retry fail"
    assert len(client.calls) == 2
    assert client.calls[1] == [
        {"role": "system", "content": "tool json"},
        {"role": "user", "content": "edit"},
    ]


def test_try_build_legacy_tool_stream_response_retries_with_compact_messages() -> None:
    client = _FakeChatClient([RuntimeError("too large"), "Recovered plain text."])
    response = try_build_legacy_tool_stream_response(_minimal_legacy_ctx(chat_client=client))
    assert response is not None
    assert len(client.calls) == 2
    assert client.calls[1] == [
        {"role": "system", "content": "tool json"},
        {"role": "user", "content": "edit"},
    ]
