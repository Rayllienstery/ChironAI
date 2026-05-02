"""Tests for delete_sentences_starting_with pipeline step."""

from __future__ import annotations

from modules.md_indexer.application.steps import step_delete_sentences_starting_with


def test_delete_sentence_starting_with_prefix_case_insensitive() -> None:
    text = (
        "Today we are going to talk about boilerplate. "
        "Core Data stores your app data. "
        "In this article we will repeat navigation text!"
    )

    out = step_delete_sentences_starting_with(
        text,
        {"prefixes": ["today we are", "in this article"]},
    )

    assert out == "Core Data stores your app data."


def test_delete_sentence_starting_with_ignores_case_sensitive_param() -> None:
    text = "APPLE documentation intro should go. Keep useful content."

    out = step_delete_sentences_starting_with(
        text,
        {"prefixes": ["apple documentation"], "case_sensitive": True},
    )

    assert out == "Keep useful content."


def test_delete_sentence_after_heading_and_blank_lines() -> None:
    text = (
        "# Using Core Data With CloudKit\n\n"
        "2019 · WWDC19 · Session 202\n\n"
        "Good morning. My name's Nick. I'm an engineer here."
    )

    out = step_delete_sentences_starting_with(
        text,
        {"prefixes": ["Good morning", "My name's"]},
    )

    assert out == "# Using Core Data With CloudKit\n\n2019 · WWDC19 · Session 202\n\nI'm an engineer here."


def test_keep_sentence_when_prefix_is_not_at_start() -> None:
    text = "Useful context says today we are shipping this API."

    out = step_delete_sentences_starting_with(
        text,
        {"prefixes": ["today we are"]},
    )

    assert out == text


def test_preserve_fenced_code_blocks() -> None:
    text = (
        "Today we are removing intro text.\n\n"
        "```swift\n"
        "Today we are not prose.\n"
        "```\n\n"
        "Keep this sentence."
    )

    out = step_delete_sentences_starting_with(
        text,
        {"prefixes": ["today we are"]},
    )

    assert out == "```swift\nToday we are not prose.\n```\n\nKeep this sentence."
