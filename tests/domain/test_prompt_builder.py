"""
Unit tests for domain.services.prompt_builder.
"""

from __future__ import annotations

import pytest

from domain.services.prompt_builder import (
    build_context_block,
    build_system_content,
    determine_reasoning_level,
    framework_filter,
    last_user_content,
)


class TestLastUserContent:
    def test_returns_last_user_message_text(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        assert last_user_content(messages) == "hello"

    def test_returns_empty_when_no_user(self) -> None:
        assert last_user_content([{"role": "assistant", "content": "hi"}]) == ""

    def test_uses_last_user(self) -> None:
        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second"},
        ]
        assert last_user_content(messages) == "second"


class TestDetermineReasoningLevel:
    def test_explicit_high(self) -> None:
        assert determine_reasoning_level("x", 50, "gpt-oss", "high") == "high"

    def test_returns_none_for_unsupported_model(self) -> None:
        assert determine_reasoning_level("x", 50, "other-model", None) is None

    def test_first_char_bang_returns_high(self) -> None:
        assert determine_reasoning_level("! complex", 50, "gpt-oss", None) == "high"


class TestFrameworkFilter:
    def test_returns_all_when_no_framework_asked(self) -> None:
        results = [{"payload": {"url": "https://a"}}]
        assert len(framework_filter("general question", results)) == 1

    def test_filters_uikit_when_asked(self) -> None:
        results = [
            {"payload": {"url": "https://uikit/doc"}},
            {"payload": {"url": "https://other/doc"}},
        ]
        out = framework_filter("uikit only", results)
        assert len(out) == 1
        assert "uikit" in out[0]["payload"]["url"]


class TestBuildContextBlock:
    def test_empty_hits_returns_empty_context(self) -> None:
        text, info, score = build_context_block([], 100, 500)
        assert text == ""
        assert info == []
        assert score == 0.0

    def test_builds_text_and_chunks_info(self) -> None:
        hits = [
            {"payload": {"text": "chunk1"}, "score": 0.9},
            {"payload": {"text": "chunk2"}, "score": 0.8},
        ]
        text, info, score = build_context_block(hits, 100, 500)
        assert "chunk1" in text
        assert len(info) >= 1
        assert score == 0.9


class TestBuildSystemContent:
    def test_includes_prefix_and_suffix(self) -> None:
        out = build_system_content("PREFIX", "SUFFIX", "ctx", 0.8, 0.75, None, "model")
        assert "PREFIX" in out
        assert "SUFFIX" in out
        assert "ctx" in out

    def test_adds_low_confidence_warning_when_below_threshold(self) -> None:
        out = build_system_content("P", "S", "ctx", 0.5, 0.75, None, "m")
        assert "0.75" in out or "low" in out.lower() or "confidence" in out.lower()
