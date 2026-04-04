"""
Domain entities for markdown ingestion and filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarkdownFile:
    """Raw markdown file from a source."""

    source_id: str
    filename: str
    content: str
    path: str = ""


@dataclass
class NormalizedMarkdown:
    """Markdown after normalization (cleaned, structured)."""

    source_id: str
    filename: str
    content: str
    path: str = ""
    url: str | None = None
    section_path: list[str] | None = None


@dataclass
class Document:
    """Document ready for chunking (normalized + metadata)."""

    source_id: str
    filename: str
    text: str
    path: str = ""
    url: str | None = None
    section_path: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class FilterRule:
    """Rule for filtering documents (e.g. by path, extension, min size)."""

    include_patterns: list[str]  # e.g. ["**/*.md"]
    exclude_patterns: list[str]  # e.g. ["**/nav.md"]
    min_size_chars: int = 0
    max_size_chars: int = 0  # 0 = no limit


@dataclass
class IngestionJob:
    """Ingestion job status and result."""

    job_id: str
    status: str  # "pending" | "running" | "done" | "failed"
    source_path: str = ""
    source_id: str = ""
    collection: str = ""
    files_processed: int = 0
    chunks_indexed: int = 0
    error: str | None = None


__all__ = [
    "MarkdownFile",
    "NormalizedMarkdown",
    "Document",
    "FilterRule",
    "IngestionJob",
]
