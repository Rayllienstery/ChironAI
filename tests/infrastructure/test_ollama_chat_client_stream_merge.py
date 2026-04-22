"""Tests for streamed Ollama assistant message merge behavior."""

from __future__ import annotations

from infrastructure.ollama.chat_client import _merge_ollama_assistant_message_parts


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

