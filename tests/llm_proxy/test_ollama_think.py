"""Tests for Ollama `think` resolution and OpenAI bridge mapping."""

from __future__ import annotations

from llm_proxy.ollama_think import coerce_think_for_model, resolve_ollama_think
from infrastructure.ollama.openai_ollama_tool_bridge import ollama_message_to_openai_assistant


def test_resolve_explicit_think_bool_wins_over_reasoning_level() -> None:
    body = {"think": False, "reasoning_effort": "high"}
    r = resolve_ollama_think(body, "high", "qwen3:latest")
    assert r is False


def test_resolve_reasoning_effort_when_no_think() -> None:
    body = {"reasoning_effort": "low"}
    r = resolve_ollama_think(body, "medium", "gpt-oss-20b")
    assert r == "low"


def test_resolve_derived_reasoning_level() -> None:
    body = {}
    r = resolve_ollama_think(body, "high", "some-model")
    assert r == "high"


def test_coerce_gpt_oss_bool_to_medium_or_false() -> None:
    assert coerce_think_for_model(True, "gpt-oss-20b") == "medium"
    assert coerce_think_for_model(False, "gpt-oss-20b") is False


def test_ollama_message_maps_thinking_to_reasoning_content() -> None:
    msg = ollama_message_to_openai_assistant(
        {"role": "assistant", "content": "answer", "thinking": "step 1..."}
    )
    assert msg.get("reasoning_content") == "step 1..."
    assert msg.get("content") == "answer"
