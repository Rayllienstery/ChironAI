"""
Domain entities for external docs fetch, ingest, and multi-collection RAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExternalSource:
    """Configuration for an external documentation source (e.g. TMArchitecture repo)."""

    id: str
    base_url: str
    paths: list[str]
    collection_name: str
    top_k: int = 2


@dataclass
class FetchedDocument:
    """A document fetched from a URL, with optional parsing metadata."""

    url: str
    content: str
    source_id: str
    filename: str
    content_type: str = "text/markdown"


@dataclass
class IngestResult:
    """Result of ingesting a source into a collection."""

    source_id: str
    collection_name: str
    documents_fetched: int
    chunks_indexed: int
    errors: list[str]


@dataclass
class RagSourceConfig:
    """Per-collection RAG config: collection name, top_k, trigger keywords, optional on-demand fetch."""

    collection_name: str
    top_k: int
    trigger_keywords: list[str]
    label: str = ""
    on_demand_fetch: bool = False
    external_source_id: str = ""


@dataclass
class RagContext:
    """Assembled RAG context for the LLM (merged from one or more collections)."""

    context_text: str
    chunks_info: list[dict[str, Any]]
    max_score: float = 0.0


__all__ = [
    "ExternalSource",
    "FetchedDocument",
    "IngestResult",
    "RagContext",
    "RagSourceConfig",
]
