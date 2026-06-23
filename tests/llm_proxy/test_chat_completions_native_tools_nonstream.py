from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from llm_proxy.chat_completions_native_tools_nonstream import (
    build_native_tools_ollama_body,
    call_native_tools_buffered_chat_with_retries,
)


def test_build_native_tools_ollama_body_includes_tools_and_think() -> None:
    chat_client = MagicMock()
    chat_client._default_options = {"temperature": 0.2}
    body = build_native_tools_ollama_body(
        chat_client=chat_client,
        use_model="llama3",
        native_ollama_messages_for_upstream=[{"role": "user", "content": "hi"}],
        ollama_think=True,
        oll_tools=[{"type": "function", "function": {"name": "search"}}],
        tool_choice_effective="auto",
        ollama_options_overlay=lambda: {"num_predict": 128},
    )
    assert body["model"] == "llama3"
    assert body["stream"] is False
    assert body["think"] is True
    assert body["tools"]
    assert "tool_choice" not in body
    assert body["options"]["num_predict"] == 128


def test_call_native_tools_buffered_chat_strips_tools_on_unsupported_error(monkeypatch: pytest.MonkeyPatch) -> None:
    trace: dict = {"request": {}}
    chat_client = MagicMock()

    class ToolsUnsupportedError(Exception):
        pass

    attempts: list[dict] = []

    def chat_api(body: dict) -> dict:
        attempts.append(dict(body))
        if "tools" in body:
            raise ToolsUnsupportedError("does not support tools")
        return {"message": {"role": "assistant", "content": "ok"}}

    chat_client.chat_api = chat_api
    monkeypatch.setattr(
        "llm_proxy.chat_completions_native_tools_nonstream.chat_error_suggests_no_tools",
        lambda exc: isinstance(exc, ToolsUnsupportedError),
    )
    result = call_native_tools_buffered_chat_with_retries(
        chat_client=chat_client,
        trace=trace,
        body_ollama={
            "model": "llama3",
            "messages": [],
            "stream": False,
            "options": {},
            "tools": [{"type": "function"}],
            "tool_choice": "auto",
        },
        native_ollama_messages=[],
        use_model="llama3",
        ollama_think=None,
        ollama_options_overlay=lambda: None,
    )

    assert len(attempts) == 2
    assert "tools" not in attempts[1]
    assert trace["request"]["native_tools_fallback"] == "stripped_tools_unsupported"
    assert result.data["message"]["content"] == "ok"


@pytest.mark.fast
def test_call_native_tools_buffered_chat_falls_back_to_chat() -> None:
    chat_client = MagicMock()
    chat_client.chat_api = None
    chat_client.chat.return_value = "plain"
    result = call_native_tools_buffered_chat_with_retries(
        chat_client=chat_client,
        trace={"request": {}},
        body_ollama={"model": "llama3", "messages": [], "stream": False, "options": {}},
        native_ollama_messages=[{"role": "user", "content": "hi"}],
        use_model="llama3",
        ollama_think=None,
        ollama_options_overlay=lambda: None,
    )
    assert result.data == {"message": {"role": "assistant", "content": "plain"}}
