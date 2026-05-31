"""Tests for OpenAI ↔ Ollama tool message bridge."""

from __future__ import annotations

import json

from rag_service.infrastructure.openai_ollama_tool_bridge import (
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
    assert ollama[2] == {"role": "tool", "tool_name": "get_temp", "name": "get_temp", "content": "22C"}


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
    assert ollama[1]["name"] == "edit_file"


def test_openai_tool_message_infers_name_from_call_id_alias() -> None:
    openai = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "id1",
                    "type": "function",
                    "function": {"name": "  edit_file  ", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "call_id": "id1", "content": "ok"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[1]["tool_name"] == "edit_file"
    assert ollama[1]["name"] == "edit_file"


def test_openai_tool_message_blank_name_falls_back_to_tool() -> None:
    openai = [
        {"role": "tool", "name": "   ", "content": "ok"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[0]["tool_name"] == "tool"
    assert ollama[0]["name"] == "tool"


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


def test_ollama_message_to_openai_assistant_recovers_dsml_tool_call_from_thinking() -> None:
    ollama_msg = {
        "role": "assistant",
        "thinking": (
            "~197KB. Let me inspect it.\n\n"
            "<｜DSML｜tool_calls>\n"
            "<｜DSML｜invoke name=\"shell\">\n"
            "<｜DSML｜parameter name=\"command\" string=\"false\">"
            "[\"powershell.exe\", \"-Command\", \"Get-ChildItem -Path api\\\\http\\\\webui_routes.py\"]"
            "</｜DSML｜parameter>\n"
            "</｜DSML｜invoke>\n"
            "</｜DSML｜tool_calls>"
        ),
        "content": "",
    }

    oa = ollama_message_to_openai_assistant(ollama_msg)

    assert oa["content"] is None
    assert oa["reasoning_content"] == "~197KB. Let me inspect it."
    assert len(oa["tool_calls"]) == 1
    tc = oa["tool_calls"][0]
    assert tc["function"]["name"] == "shell"
    args = json.loads(tc["function"]["arguments"])
    assert args == {"command": ["powershell.exe", "-Command", "Get-ChildItem -Path api\\http\\webui_routes.py"]}
    assert openai_finish_reason_from_ollama(ollama_msg) == "tool_calls"


def test_openai_finish_reason_length_from_ollama_done_reason() -> None:
    msg = {"role": "assistant", "content": "hi"}
    assert openai_finish_reason_from_ollama(msg) == "stop"
    assert openai_finish_reason_from_ollama(msg, "length") == "length"
    assert openai_finish_reason_from_ollama(msg, "LENGTH") == "length"


def test_ollama_tools_from_openai_filters_non_dict() -> None:
    assert ollama_tools_from_openai([{"type": "function", "function": {"name": "n"}}]) is not None
    assert ollama_tools_from_openai([]) is None


def test_ollama_tools_from_openai_drops_unsupported_types_and_blank_names() -> None:
    tools = [
        {"type": "web_search"},
        {"type": "function", "function": {"name": "   ", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "ok", "parameters": {"type": "object"}}},
    ]
    out = ollama_tools_from_openai(tools) or []
    assert len(out) == 1
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "ok"


def test_ollama_tools_from_openai_accepts_flat_function_shape() -> None:
    out = ollama_tools_from_openai(
        [{"type": "function", "name": "shell", "description": "Run shell", "parameters": {"type": "object"}}]
    )
    assert out is not None
    assert out[0]["function"]["name"] == "shell"
    assert out[0]["function"]["description"] == "Run shell"


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


def test_openai_messages_preserve_thought_signature_on_tool_calls() -> None:
    """Gemini 3 via Ollama Cloud requires thought_signature on tool calls across turns."""
    openai = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "signature": "msg-sig-1",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "get_temp",
                        "arguments": '{"city":"NYC"}',
                        "thought_signature": "Z2VtaW5pLXNpZw==",
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_abc", "content": "22C"},
    ]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[1]["role"] == "assistant"
    assert ollama[1]["signature"] == "msg-sig-1"
    tc0 = ollama[1]["tool_calls"][0]
    fn0 = tc0["function"]
    assert fn0["thought_signature"] == "Z2VtaW5pLXNpZw=="
    assert ((tc0.get("extra_content") or {}).get("google") or {}).get("thought_signature") == "Z2VtaW5pLXNpZw=="
    assert fn0["name"] == "get_temp"
    assert fn0["arguments"] == {"city": "NYC"}


def test_openai_messages_preserve_tool_call_id_for_ollama_roundtrip() -> None:
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
    ]
    ollama = openai_messages_to_ollama(openai)
    tc0 = ollama[1]["tool_calls"][0]
    assert tc0["id"] == "call_abc"
    assert tc0["call_id"] == "call_abc"


def test_openai_messages_adds_validator_skip_thought_signature_when_missing() -> None:
    openai = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "get_temp",
                        "arguments": '{"city":"NYC"}',
                    },
                }
            ],
        },
    ]
    ollama = openai_messages_to_ollama(openai)
    tc0 = ollama[1]["tool_calls"][0]
    fn0 = tc0["function"]
    assert fn0["thought_signature"] == "skip_thought_signature_validator"
    assert ((tc0.get("extra_content") or {}).get("google") or {}).get(
        "thought_signature"
    ) == "skip_thought_signature_validator"


def test_openai_messages_reads_thought_signature_from_extra_content_alias() -> None:
    openai = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "extra_content": {"google": {"thought_signature": "sig_from_extra"}},
                    "function": {
                        "name": "get_temp",
                        "arguments": '{"city":"NYC"}',
                    },
                }
            ],
        },
    ]
    ollama = openai_messages_to_ollama(openai)
    tc0 = ollama[1]["tool_calls"][0]
    assert tc0["function"]["thought_signature"] == "sig_from_extra"
    assert ((tc0.get("extra_content") or {}).get("google") or {}).get(
        "thought_signature"
    ) == "sig_from_extra"


def test_ollama_message_to_openai_preserves_thought_signature_and_message_signature() -> None:
    ollama_msg = {
        "role": "assistant",
        "content": "",
        "signature": "roundtrip-msg",
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "rag_query",
                    "arguments": {"query": "x"},
                    "thought_signature": "abc123",
                },
            }
        ],
    }
    oa = ollama_message_to_openai_assistant(ollama_msg)
    assert oa["signature"] == "roundtrip-msg"
    assert oa["tool_calls"][0]["function"]["name"] == "rag_query"
    assert oa["tool_calls"][0]["function"]["thought_signature"] == "abc123"
    assert ((oa["tool_calls"][0].get("extra_content") or {}).get("google") or {}).get(
        "thought_signature"
    ) == "abc123"
    args = json.loads(oa["tool_calls"][0]["function"]["arguments"])
    assert args == {"query": "x"}


def test_ollama_message_to_openai_preserves_tool_call_id() -> None:
    oa = ollama_message_to_openai_assistant(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "id_from_ollama",
                    "type": "function",
                    "function": {"name": "x", "arguments": {"a": 1}},
                }
            ],
        }
    )
    assert oa["tool_calls"][0]["id"] == "id_from_ollama"
    assert oa["tool_calls"][0]["call_id"] == "id_from_ollama"


def test_assistant_signature_preserved_without_tool_calls() -> None:
    openai = [{"role": "assistant", "content": "ok", "signature": "s-only"}]
    ollama = openai_messages_to_ollama(openai)
    assert ollama[0] == {"role": "assistant", "content": "ok", "signature": "s-only"}
    oa = ollama_message_to_openai_assistant(ollama[0])
    assert oa["signature"] == "s-only"
    assert oa["content"] == "ok"
