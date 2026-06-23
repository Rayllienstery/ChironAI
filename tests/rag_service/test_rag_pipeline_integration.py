"""Integration test for the full RAG pipeline end-to-end with in-memory ports.

This test exercises the real application use cases (`search_rag`,
`build_rag_context`, `answer_question`) against fake implementations of the
RagRepository, EmbeddingProvider, RerankClient, and ChatLLMClient ports.
It does not require a running Qdrant or Ollama instance.
"""

from __future__ import annotations

from typing import Any

import pytest
from rag_service.application.use_cases import answer_question, build_rag_context, search_rag
from rag_service.domain.entities import RagQuestionRequest
from rag_service.domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient


class FakeEmbeddingProvider:
    """Deterministic embedding: each token maps to a fixed dimension vector."""

    def __init__(self, dim: int = 4) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        base = [0.0] * self.dim
        for i, ch in enumerate(text):
            base[i % self.dim] += ord(ch) / 255.0
        return base

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeRagRepository:
    """In-memory vector store seeded with chunks. Search returns cosine-like matches."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks

    def get_collection_name(self) -> str:
        return "fake-collection"

    def supports_hybrid(self) -> bool:
        return False

    def search(
        self,
        vector: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None = None,
        *,
        sparse_indices: list[int] | None = None,
        sparse_values: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        def _dot(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        scored = []
        for chunk in self.chunks:
            emb = chunk.get("embedding")
            if emb is None:
                continue
            score = _dot(vector, emb)
            if score > 0:
                scored.append({"score": score, **chunk})
        scored.sort(key=lambda h: h["score"], reverse=True)
        return scored[:top_k]


class FakeRerankClient:
    """Reranker that keeps the original order but assigns descending scores."""

    def rerank(self, question: str, prompt_text: str) -> str | None:
        return None


class FakeChatLLMClient:
    """Records the messages it receives and returns a canned answer."""

    def __init__(self, answer: str = "fake answer") -> None:
        self.answer = answer
        self.last_messages: list[dict[str, Any]] | None = None

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> str:
        self.last_messages = messages
        return self.answer

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Any:
        yield self.answer


@pytest.fixture
def embed_provider() -> EmbeddingProvider:
    return FakeEmbeddingProvider(dim=4)  # type: ignore[return-value]


@pytest.fixture
def rerank_client() -> RerankClient:
    return FakeRerankClient()  # type: ignore[return-value]


@pytest.fixture
def chat_client() -> ChatLLMClient:
    return FakeChatLLMClient(answer="integration answer")  # type: ignore[return-value]


@pytest.fixture
def rag_repo(embed_provider: EmbeddingProvider) -> RagRepository:
    chunks = [
        {
            "id": "chunk-1",
            "payload": {
                "text": "SwiftUI List provides swipe actions for editing rows.",
                "url": "https://example.com/swiftui-list",
                "doc_type": "documentation",
            },
            "embedding": embed_provider.embed("swiftui list swipe actions"),
        },
        {
            "id": "chunk-2",
            "payload": {
                "text": "UIKit UITableView uses UISwipeActionsConfiguration for row actions.",
                "url": "https://example.com/uikit-tableview",
                "doc_type": "documentation",
            },
            "embedding": embed_provider.embed("uikit tableview swipe actions"),
        },
        {
            "id": "chunk-3",
            "payload": {
                "text": "Combine framework publishers handle asynchronous events.",
                "url": "https://example.com/combine",
                "doc_type": "documentation",
            },
            "embedding": embed_provider.embed("combine publishers"),
        },
    ]
    return FakeRagRepository(chunks)  # type: ignore[return-value]


@pytest.mark.integration
@pytest.mark.slow
class TestRagPipelineIntegration:
    """End-to-end RAG pipeline using real use-case orchestration and fake ports."""

    def test_search_rag_returns_relevant_chunks(
        self,
        rag_repo: RagRepository,
        embed_provider: EmbeddingProvider,
        rerank_client: RerankClient,
    ) -> None:
        hits, timings, rerank_pool = search_rag(
            "SwiftUI List swipe actions",
            rag_repo,
            embed_provider,
            rerank_client,
            top_k=2,
        )
        assert len(hits) > 0
        assert any("SwiftUI" in (h.get("payload", {}).get("text") or "") for h in hits)
        assert "search_s" in timings
        assert "embed_s" in timings
        assert len(rerank_pool) >= len(hits)

    def test_build_rag_context_assembles_context_text(
        self,
        rag_repo: RagRepository,
        embed_provider: EmbeddingProvider,
        rerank_client: RerankClient,
    ) -> None:
        ctx, timings = build_rag_context(
            "SwiftUI List swipe actions",
            rag_repo,
            embed_provider,
            rerank_client,
            context_chunk_chars=500,
            context_total_chars=2000,
            top_k=2,
            force_rag=True,
        )
        assert ctx.context_text
        assert len(ctx.chunks_info) > 0
        assert any("SwiftUI" in ci.get("text_preview", "") for ci in ctx.chunks_info)
        assert timings["total_rag_s"] >= 0.0

    def test_answer_question_uses_rag_context_in_system_message(
        self,
        rag_repo: RagRepository,
        embed_provider: EmbeddingProvider,
        rerank_client: RerankClient,
        chat_client: ChatLLMClient,
    ) -> None:
        request = RagQuestionRequest(
            messages=[{"role": "user", "content": "SwiftUI List swipe actions"}],
            model="fake-model",
        )
        response = answer_question(
            request,
            rag_repo,
            embed_provider,
            rerank_client,
            chat_client,
            system_prefix="You are a helpful assistant.",
            system_suffix="",
            context_chunk_chars=500,
            context_total_chars=2000,
            confidence_threshold=0.5,
            model_name="fake-model",
            force_rag=True,
        )
        assert response.content == "integration answer"
        assert response.model == "fake-model"
        assert chat_client.last_messages is not None
        system_msg = chat_client.last_messages[0]
        assert system_msg["role"] == "system"
        assert "SwiftUI" in system_msg["content"]

    def test_answer_question_with_provided_context_skips_retrieval(
        self,
        rag_repo: RagRepository,
        embed_provider: EmbeddingProvider,
        rerank_client: RerankClient,
        chat_client: ChatLLMClient,
    ) -> None:
        from rag_service.domain.entities import RagContext

        provided = RagContext(
            context_text="Provided context about SwiftUI navigation.",
            chunks_info=[{"index": 1, "text_preview": "SwiftUI navigation"}],
            max_score=0.9,
        )
        request = RagQuestionRequest(
            messages=[{"role": "user", "content": "Tell me about SwiftUI navigation"}],
            model="fake-model",
        )
        response = answer_question(
            request,
            rag_repo,
            embed_provider,
            rerank_client,
            chat_client,
            system_prefix="",
            system_suffix="",
            context_chunk_chars=500,
            context_total_chars=2000,
            confidence_threshold=0.5,
            model_name="fake-model",
            rag_context=provided,
        )
        assert response.content == "integration answer"
        system_msg = chat_client.last_messages[0]
        assert "Provided context about SwiftUI navigation." in system_msg["content"]
