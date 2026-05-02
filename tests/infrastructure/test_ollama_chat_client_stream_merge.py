"""Tests for streamed Ollama assistant message merge behavior."""

from __future__ import annotations

import json

import pytest

import infrastructure.ollama.chat_client as chat_client_module
from infrastructure.ollama.chat_client import OllamaChatClient, _merge_ollama_assistant_message_parts


def test_merge_tool_calls_preserves_thought_signature_across_chunks() -> None:
    merged = _merge_ollama_assistant_message_parts(
        {},
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "index": 0,
                        "name": "glob",
                        "arguments": {"pattern": "*"},
                        "thought_signature": "sig_a",
                    },
                }
            ]
        },
    )
    merged = _merge_ollama_assistant_message_parts(
        merged,
        {
            "tool_calls": [
                {
                    "call_id": "call_1",
                    "type": "function",
                    "function": {
                        "index": 0,
                        "name": "glob",
                        "arguments": {"pattern": "*.md"},
                    },
                }
            ]
        },
    )

    tc = merged["tool_calls"][0]
    assert tc["id"] == "call_1"
    assert tc["call_id"] == "call_1"
    assert tc["function"]["arguments"] == {"pattern": "*.md"}
    assert tc["function"]["thought_signature"] == "sig_a"
    assert ((tc.get("extra_content") or {}).get("google") or {}).get("thought_signature") == "sig_a"


def test_merge_tool_calls_keeps_existing_when_later_chunk_empty() -> None:
    merged = _merge_ollama_assistant_message_parts(
        {},
        {
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "read", "arguments": {"filePath": "TODO.md"}},
                }
            ]
        },
    )
    merged2 = _merge_ollama_assistant_message_parts(merged, {"tool_calls": []})
    assert merged2["tool_calls"][0]["id"] == "call_2"
    assert merged2["tool_calls"][0]["function"]["name"] == "read"


def test_iter_chat_api_stream_events_separates_thinking_and_final_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, decode_unicode: bool = True):  # noqa: ARG002
            rows = [
                {"message": {"thinking": "Plan"}},
                {"message": {"thinking": "Plan more", "content": "Answer"}},
                {"done": True, "message": {"thinking": "Plan more", "content": "Answer done"}},
            ]
            for row in rows:
                yield json.dumps(row)

        def close(self) -> None:
            return None

    monkeypatch.setattr(chat_client_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    client = OllamaChatClient(base_url="http://example.test/api/chat", model="fake")
    events = list(client.iter_chat_api_stream_events({"model": "fake", "messages": []}))

    assert [item for item in events if item[0] in {"thinking_delta", "content_delta"}] == [
        ("thinking_delta", "Plan"),
        ("thinking_delta", " more"),
        ("content_delta", "Answer"),
        ("content_delta", " done"),
    ]
    assert events[-1][0] == "done"


def test_iter_chat_api_stream_openai_parts_keeps_visible_stream_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, decode_unicode: bool = True):  # noqa: ARG002
            rows = [
                {"message": {"thinking": "Plan"}},
                {"message": {"thinking": "Plan more", "content": "Answer"}},
                {"done": True, "message": {"thinking": "Plan more", "content": "Answer done"}},
            ]
            for row in rows:
                yield json.dumps(row)

        def close(self) -> None:
            return None

    monkeypatch.setattr(chat_client_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    client = OllamaChatClient(base_url="http://example.test/api/chat", model="fake")
    parts = list(client.iter_chat_api_stream_openai_parts({"model": "fake", "messages": []}))

    assert parts == [
        ("content", "Plan"),
        ("content", " more"),
        ("content", "Answer"),
        ("content", " done"),
    ]


def test_iter_chat_api_stream_events_errors_when_stream_closes_without_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, decode_unicode: bool = True):  # noqa: ARG002
            yield json.dumps({"message": {"content": "partial only"}})

        def close(self) -> None:
            return None

    monkeypatch.setattr(chat_client_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    client = OllamaChatClient(base_url="http://example.test/api/chat", model="fake")
    events = list(client.iter_chat_api_stream_events({"model": "fake", "messages": []}))

    assert events[-1][0] == "error"
    assert "without a terminal done chunk" in events[-1][1]


def test_iter_chat_api_stream_events_disables_requests_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, decode_unicode: bool = True):  # noqa: ARG002
            yield json.dumps({"message": {"content": "ok"}})
            yield json.dumps({"done": True, "message": {"content": "ok"}})

        def close(self) -> None:
            return None

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        seen_kwargs.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(chat_client_module.requests, "post", fake_post)

    client = OllamaChatClient(base_url="http://example.test/api/chat", model="fake")
    events = list(client.iter_chat_api_stream_events({"model": "fake", "messages": []}))

    assert seen_kwargs["timeout"] is None
    assert events[-1][0] == "done"


def test_chat_api_stream_final_disables_requests_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_kwargs: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, decode_unicode: bool = True):  # noqa: ARG002
            yield json.dumps({"message": {"content": "final"}})
            yield json.dumps({"done": True, "message": {"content": "final"}})

        def close(self) -> None:
            return None

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        seen_kwargs.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(chat_client_module.requests, "post", fake_post)

    client = OllamaChatClient(base_url="http://example.test/api/chat", model="fake")
    result = client.chat_api_stream_final({"model": "fake", "messages": []})

    assert seen_kwargs["timeout"] is None
    assert result["message"]["content"] == "final"
