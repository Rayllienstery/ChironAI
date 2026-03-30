"""Tests for transparent think passthrough and merged assistant content (no reasoning_content)."""

from __future__ import annotations

from llm_proxy.chat_completions import (
    _is_micro_garbage_reply,
    _is_placeholder_only_reply,
    effective_ollama_think_from_body,
    passthrough_think_from_body,
)
from infrastructure.ollama.openai_ollama_tool_bridge import ollama_message_to_openai_assistant


def test_effective_think_forces_false_for_qwen3() -> None:
    assert effective_ollama_think_from_body({}, "qwen3.5:9b") is False
    assert effective_ollama_think_from_body({"think": True}, "qwen3.5:9b") is False
    assert effective_ollama_think_from_body({"think": False}, "qwen3.5:9b") is False
    assert effective_ollama_think_from_body({"think": "high"}, "Qwen3:latest") is False
    assert effective_ollama_think_from_body({}, "llama3.2:latest") is None
    assert effective_ollama_think_from_body({"think": True}, "llama3.2:latest") is True


def test_passthrough_think_only_when_body_contains_key() -> None:
    assert passthrough_think_from_body({}) is None
    assert passthrough_think_from_body({"think": True}) is True
    assert passthrough_think_from_body({"think": False}) is False
    assert passthrough_think_from_body({"think": "medium"}) == "medium"
    assert passthrough_think_from_body({"think": 1}) is True
    assert passthrough_think_from_body({"think": 0}) is False


def test_ollama_message_merges_thinking_into_content() -> None:
    msg = ollama_message_to_openai_assistant(
        {"role": "assistant", "content": "answer", "thinking": "step 1..."}
    )
    assert msg.get("reasoning_content") is None
    assert msg.get("content") == "step 1...\n\nanswer"


def test_is_micro_garbage_reply_detects_single_cyrillic_word() -> None:
    assert _is_micro_garbage_reply("установке") is True
    assert _is_micro_garbage_reply("hello world") is False


def test_is_placeholder_only_reply_detects_dot_only() -> None:
    assert _is_placeholder_only_reply(".") is True
    assert _is_placeholder_only_reply("  .  ") is True
    assert _is_placeholder_only_reply("") is True
    assert _is_placeholder_only_reply("hello") is False
    assert _is_placeholder_only_reply("a" * 121) is False


def test_ollama_message_thinking_only_still_content() -> None:
    msg = ollama_message_to_openai_assistant({"role": "assistant", "thinking": "only think"})
    assert msg.get("reasoning_content") is None
    assert msg.get("content") == "only think"
