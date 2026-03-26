"""
Unit tests for application.rag.use_cases with mocked ports.
"""

from __future__ import annotations

import pytest

from application.rag.use_cases import build_rag_context, prepare_ollama_messages, search_rag
from domain.entities.rag import RagContext, RagQuestionRequest


class MockRagRepo:
    def __init__(self, search_call_count: list[int] | None = None):
        self._search_call_count = search_call_count if search_call_count is not None else []

    def get_collection_name(self) -> str:
        return "test"

    def search(self, vector, top_k, filter_dict=None):
        if self._search_call_count is not None:
            self._search_call_count.append(1)
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
    ctx, timings = build_rag_context(
        "What is SwiftUI?",
        MockRagRepo(),
        MockEmbed(),
        MockRerank(),
        500,
        2000,
    )
    assert isinstance(ctx, RagContext)
    assert (
        "embed_s" in timings
        and "search_s" in timings
        and "rerank_s" in timings
        and "embed_tokens_in" in timings
        and "rerank_prompt_tokens_in" in timings
    )
    assert "chunk" in ctx.context_text.lower()
    assert ctx.max_score >= 0.8


def test_build_rag_context_empty_question_returns_empty() -> None:
    ctx, _ = build_rag_context("", MockRagRepo(), MockEmbed(), MockRerank(), 500, 2000)
    assert ctx.context_text == ""
    assert ctx.max_score == 0.0


def test_build_rag_context_skips_rag_for_greeting() -> None:
    search_calls: list[int] = []
    repo = MockRagRepo(search_call_count=search_calls)
    ctx, timings = build_rag_context("hi", repo, MockEmbed(), MockRerank(), 500, 2000)
    assert ctx.context_text == ""
    assert timings.get("embed_s", 0) == 0 and timings.get("search_s", 0) == 0
    assert ctx.chunks_info == []
    assert ctx.max_score == 0.0
    assert len(search_calls) == 0


def test_build_rag_context_uses_rag_when_keyword_present() -> None:
    search_calls: list[int] = []
    repo = MockRagRepo(search_call_count=search_calls)
    ctx, _ = build_rag_context(
        "What is SwiftUI?",
        repo,
        MockEmbed(),
        MockRerank(),
        500,
        2000,
    )
    assert ctx.context_text != ""
    assert len(ctx.chunks_info) >= 1
    assert ctx.max_score >= 0.8
    assert len(search_calls) >= 1


def test_build_rag_context_with_custom_keywords_skips_when_no_match() -> None:
    search_calls: list[int] = []
    repo = MockRagRepo(search_call_count=search_calls)
    ctx, _ = build_rag_context(
        "what is the weather?",
        repo,
        MockEmbed(),
        MockRerank(),
        500,
        2000,
        rag_required_keywords=["swift", "ios", "code"],
    )
    assert ctx.context_text == ""
    assert ctx.chunks_info == []
    assert len(search_calls) == 0


def test_build_rag_context_with_custom_keywords_uses_rag_when_match() -> None:
    search_calls: list[int] = []
    repo = MockRagRepo(search_call_count=search_calls)
    ctx, _ = build_rag_context(
        "explain Swift",
        repo,
        MockEmbed(),
        MockRerank(),
        500,
        2000,
        rag_required_keywords=["swift", "ios"],
    )
    assert ctx.context_text != ""
    assert len(ctx.chunks_info) >= 1
    assert len(search_calls) >= 1


def test_search_rag_returns_list() -> None:
    results, timings = search_rag("SwiftUI View", MockRagRepo(), MockEmbed(), MockRerank())
    assert isinstance(results, list)
    assert len(results) >= 1
    assert (
        "embed_s" in timings
        and "search_s" in timings
        and "rerank_s" in timings
        and "embed_tokens_in" in timings
        and "rerank_prompt_tokens_in" in timings
    )


def test_prepare_ollama_messages_keeps_tool_cycle_context() -> None:
    req = RagQuestionRequest(
        messages=[
            {"role": "user", "content": "Please edit file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "apply_file_edit", "arguments": '{"file_path":"a.py"}'},
                    }
                ],
            },
            {"role": "tool", "name": "apply_file_edit", "content": '{"ok":true}'},
        ],
        model="rag-ollama",
        stream=False,
        reasoning_level=None,
    )
    msgs, model = prepare_ollama_messages(
        req,
        MockRagRepo(),
        MockEmbed(),
        None,
        "prefix",
        "suffix",
        500,
        2000,
        0.0,
        "model-x",
        rag_context=RagContext("", [], 0.0),
    )
    joined = "\n".join(m.get("content", "") for m in msgs if isinstance(m, dict))
    assert "[tool_call:apply_file_edit]" in joined
    assert "[tool_result:apply_file_edit]" in joined
    assert model == "rag-ollama"


def test_prepare_ollama_messages_infers_tool_result_name_from_tool_call_id() -> None:
    req = RagQuestionRequest(
        messages=[
            {"role": "user", "content": "Please edit file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "apply_file_edit", "arguments": '{"file_path":"a.py"}'},
                    }
                ],
            },
            # ZED/OpenAI-compatible tool-results may omit `name` and provide only `tool_call_id`.
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok":true}'},
        ],
        model="rag-ollama",
        stream=False,
        reasoning_level=None,
    )
    msgs, model = prepare_ollama_messages(
        req,
        MockRagRepo(),
        MockEmbed(),
        None,
        "prefix",
        "suffix",
        500,
        2000,
        0.0,
        "model-x",
        rag_context=RagContext("", [], 0.0),
    )
    joined = "\n".join(m.get("content", "") for m in msgs if isinstance(m, dict))
    assert "[tool_call:apply_file_edit]" in joined
    assert "[tool_result:apply_file_edit]" in joined
    assert model == "rag-ollama"
