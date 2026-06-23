"""Tests for RAG test Markdown authoring helpers."""

from __future__ import annotations

from application.rag_tests.authoring import build_rag_test_markdown, normalize_concepts


def test_normalize_concepts_splits_simple_atomic_lists() -> None:
    assert normalize_concepts([" weak / unowned ", "", "MainActor and Sendable"]) == [
        "weak",
        "unowned",
        "MainActor",
        "Sendable",
    ]


def test_normalize_concepts_keeps_long_ambiguous_phrase() -> None:
    text = "Use task groups and cancellation carefully when coordinating nested child tasks"

    assert normalize_concepts([text]) == [text]


def test_build_rag_test_markdown_includes_optional_fields() -> None:
    content = build_rag_test_markdown(
        name="Concurrency Basics",
        question="How should cancellation be handled?",
        concepts=["Task cancellation"],
        platform="Apple",
        framework="Swift",
        difficulty="medium",
        concept_mode="all",
        rag_strict=True,
        min_os="iOS 17",
        notes="Prefer source-backed answers.",
    )

    assert "# Concurrency Basics" in content
    assert "RAG Strict: true" in content
    assert "MinOS: iOS 17" in content
    assert "- Task cancellation" in content
    assert "Prefer source-backed answers." in content
