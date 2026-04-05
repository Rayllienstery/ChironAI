"""
Domain entities for RAG.

Simple data structures used across retrieval and chat flows.
No infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RagChunk:
    """
    A single retrieved chunk with score and payload.

    id: point id from vector store.
    score: similarity score (e.g. from Qdrant).
    rerank_score: optional, 1/rank after reranking.
    payload: raw payload (text, url, path, doc_type, ios_versions, swift_versions, etc.).
    """

    id: str | int
    score: float
    payload: dict[str, Any]
    rerank_score: float | None = None

    @property
    def text(self) -> str:
        return (self.payload.get("text") or "").strip()

    @property
    def url(self) -> str:
        return self.payload.get("url") or ""

    @property
    def doc_type(self) -> str:
        return (self.payload.get("doc_type") or "documentation").lower()


@dataclass
class RagContext:
    """
    Assembled RAG context for the LLM: concatenated text and metadata for logging.
    """

    context_text: str
    chunks_info: list[dict[str, Any]]
    max_score: float = 0.0
    retrieval_skipped: bool = False


@dataclass
class RagQuestionRequest:
    """Request for answering a question with RAG."""

    messages: list[dict[str, Any]]
    model: str | None = None
    stream: bool = False
    reasoning_level: str | None = None


@dataclass
class RagAnswerResponse:
    """Response from the RAG answer use case."""

    content: str
    model: str
    finish_reason: str = "stop"


__all__ = [
    "RagChunk",
    "RagContext",
    "RagQuestionRequest",
    "RagAnswerResponse",
]
