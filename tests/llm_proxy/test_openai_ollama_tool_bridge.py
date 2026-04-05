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


def test_openai_finish_reason_length_from_ollama_done_reason() -> None:
    msg = {"role": "assistant", "content": "hi"}
    assert openai_finish_reason_from_ollama(msg) == "stop"
    assert openai_finish_reason_from_ollama(msg, "length") == "length"
    assert openai_finish_reason_from_ollama(msg, "LENGTH") == "length"


def test_ollama_tools_from_openai_filters_non_dict() -> None:
    assert ollama_tools_from_openai([{"type": "function", "function": {"name": "n"}}]) is not None
    assert ollama_tools_from_openai([]) is None


def test_arguments_to_openai_string() -> None:
    assert arguments_to_openai_string({"a": True}) == '{"a": true}'


def test_openai_messages_system_multipart_list_not_python_repr() -> None:
    openai = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "Line A"},
                {"type": "text", "text": "Line B"},
            ],
        },
        {"role": "user", "content": "ok"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[0]["role"] == "system"
    assert "Line A" in ollama[0]["content"]
    assert "Line B" in ollama[0]["content"]
    assert not ollama[0]["content"].startswith("[")


def test_openai_messages_developer_maps_to_system() -> None:
    openai = [{"role": "developer", "content": "dev rules"}, {"role": "user", "content": "hi"}]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[0] == {"role": "system", "content": "dev rules"}
    assert ollama[1]["role"] == "user"


def test_openai_unknown_role_preserved_as_user() -> None:
    openai = [{"role": "custom", "content": "payload"}]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[0]["role"] == "user"
    assert "custom" in ollama[0]["content"]
    assert "payload" in ollama[0]["content"]
