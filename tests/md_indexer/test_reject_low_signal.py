"""Tests for reject_low_signal_body pipeline step."""

from __future__ import annotations

from modules.md_indexer.application.steps import (
    DEFAULT_REJECT_LOW_SIGNAL_PARAMS,
    step_reject_low_signal_body,
)


def test_reject_when_below_min_chars() -> None:
    assert step_reject_low_signal_body("hello world", {"min_chars": 200}) == ""


def test_keep_short_dense_prose_above_threshold() -> None:
    text = "word " * 45  # >200 chars, many words, good alpha
    out = step_reject_low_signal_body(text, dict(DEFAULT_REJECT_LOW_SIGNAL_PARAMS))
    assert out == text


def test_reject_few_words_even_if_chars_ok() -> None:
    text = "a" * 250
    out = step_reject_low_signal_body(text, {"min_chars": 200, "min_words": 5, "min_alpha_ratio": 0})
    assert out == ""


def test_reject_low_alpha_ratio() -> None:
    text = "[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]()[]() " * 8
    assert len(text.strip()) >= 200
    out = step_reject_low_signal_body(
        text,
        {"min_chars": 200, "min_words": 0, "min_alpha_ratio": 0.12},
    )
    assert out == ""
