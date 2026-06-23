"""
Crawler service API contract: DTOs for HTTP clients and subprocess callers.

REST shape (future HTTP service) is documented inline; this module provides typed records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict, cast


class CrawlSourceDict(TypedDict, total=False):
    """Shape of one entry in config/sources.yaml (subset; extra keys allowed)."""

    id: str
    url: str
    max_depth: int
    crawler: str
    doc_only: bool
    seed_urls: list[str]
    path_prefixes: list[str]
    excluded_path_substrings: list[str]
    extra: dict[str, Any]


class CrawlStartRequestBody(TypedDict, total=False):
    """POST /crawl/start body (planned)."""

    source_id: str
    source_ids: list[str]


class CrawlStartResponse(TypedDict):
    """POST /crawl/start response (planned)."""

    job_id: str
    status: Literal["started"]


class CrawlStatusResponse(TypedDict, total=False):
    """GET /crawl/status/{job_id} response (planned)."""

    status: Literal["running", "done", "failed", "not_running"]
    sources_crawled: int
    pages: int
    error: str | None
    source_id: str


@dataclass
class CrawlPageResult:
    """One fetched page (in-process or serialized)."""

    url: str
    html: str
    source_id: str
    extra: dict[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))


__all__ = [
    "CrawlSourceDict",
    "CrawlStartRequestBody",
    "CrawlStartResponse",
    "CrawlStatusResponse",
    "CrawlPageResult",
]
