"""Tests for OpenAI ↔ Ollama tool message bridge."""

from __future__ import annotations

import json

from infrastructure.ollama.openai_ollama_tool_bridge import (
    arguments_to_ollama_object,
    arguments_to_openai_string,
    openai_finish_reason_from_ollama,
    openai_messages_to_ollama,
    ollama_message_to_openai_assistant,
    ollama_tools_from_openai,
)


def test_arguments_to_ollama_object_parses_json_string() -> None:
    assert arguments_to_ollama_object('{"a": 1}') == {"a": 1}
    assert arguments_to_ollama_object({}) == {}
    assert arguments_to_ollama_object("") == {}


def test_openai_messages_single_tool_roundtrip_shape() -> None:
    openai = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "get_temp", "arguments": '{"city":"NYC"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_abc", "content": "22C"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[1]["role"] == "assistant"
    assert ollama[1]["tool_calls"][0]["function"]["arguments"] == {"city": "NYC"}
    assert ollama[2] == {"role": "tool", "tool_name": "get_temp", "content": "22C"}


def test_openai_tool_message_infers_name_from_tool_call_id() -> None:
    openai = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "id1",
                    "type": "function",
                    "function": {"name": "edit_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "id1", "content": "ok"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[1]["tool_name"] == "edit_file"


def test_ollama_message_to_openai_assistant_tool_calls() -> None:
    ollama_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "foo",
                    "arguments": {"x": 1},
                },
            }
        ],
    }
    oa = ollama_message_to_openai_assistant(ollama_msg)
    assert oa["role"] == "assistant"
    assert "tool_calls" in oa
    assert oa["tool_calls"][0]["function"]["name"] == "foo"
    args = json.loads(oa["tool_calls"][0]["function"]["arguments"])
    assert args == {"x": 1}
    assert openai_finish_reason_from_ollama(ollama_msg) == "tool_calls"


def test_ollama_tools_from_openai_filters_non_dict() -> None:
    assert ollama_tools_from_openai([{"type": "function", "function": {"name": "n"}}]) is not None
    assert ollama_tools_from_openai([]) is None


def test_arguments_to_openai_string() -> None:
    assert arguments_to_openai_string({"a": True}) == '{"a": true}'
