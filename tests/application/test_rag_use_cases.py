"""
Unit tests for application.rag.use_cases with mocked ports.
"""

from __future__ import annotations

import pytest

from application.rag.use_cases import build_rag_context, search_rag
from domain.entities.rag import RagContext


class MockRagRepo:
    def get_collection_name(self) -> str:
        return "test"

    def search(self, vector, top_k, filter_dict=None):
        return [
            {"id": "1", "score": 0.9, "payload": {"text": "chunk one"}},
            {"id": "2", "score": 0.8, "payload": {"text": "chunk two"}},
        ]


class MockEmbed:
    def embed(self, text: str):
        return [0.1] * 64

    def embed_batch(self, texts):
        return [[0.1] * 64] * len(texts)


class MockRerank:
    def rerank(self, question: str, prompt_text: str):
        return "[2, 1]"


def test_build_rag_context_returns_rag_context() -> None:
    ctx = build_rag_context(
        "What is SwiftUI?",
        MockRagRepo(),
        MockEmbed(),
        MockRerank(),
        500,
        2000,
    )
    assert isinstance(ctx, RagContext)
    assert "chunk" in ctx.context_text.lower()
    assert ctx.max_score >= 0.8


def test_build_rag_context_empty_question_returns_empty() -> None:
    ctx = build_rag_context("", MockRagRepo(), MockEmbed(), MockRerank(), 500, 2000)
    assert ctx.context_text == ""
    assert ctx.max_score == 0.0


def test_search_rag_returns_list() -> None:
    results = search_rag("SwiftUI View", MockRagRepo(), MockEmbed(), MockRerank())
    assert isinstance(results, list)
    assert len(results) >= 1
