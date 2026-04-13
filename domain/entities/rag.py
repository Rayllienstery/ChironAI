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
    #: True when retrieval was not run (e.g. client ``skip_rag``); avoids "zero hits" boilerplate in system prompt.
    retrieval_skipped: bool = False
    #: Ordered pipeline steps for UI (e.g. RAG timeline); optional.
    rag_trace: list[dict[str, Any]] | None = None
    #: Heuristic concept coverage over selected hits (see ``compute_concept_coverage_report``).
    coverage_report: dict[str, Any] | None = None
    #: High-level RAG quality hint for clients and logs (e.g. failure_class).
    rag_quality: dict[str, Any] | None = None


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


@dataclass
class QueryIntent:
    """
    Parsed intent for a RAG question, used to build metadata filters
    and adjust document priority.

    symbol: API symbol or type name (e.g. UIViewController, handleEvents).
    framework: High-level technology/framework (e.g. uikit, swiftui, combine).
    section_hint: Optional section preference (e.g. discussion, overview, examples).
    """

    symbol: str | None = None
    framework: str | None = None
    section_hint: str | None = None


__all__ = [
    "RagChunk",
    "RagContext",
    "RagQuestionRequest",
    "RagAnswerResponse",
    "QueryIntent",
]
