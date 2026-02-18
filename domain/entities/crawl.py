"""
Domain entities for crawling and indexing.

Minimal data structures for crawl sources, results, and indexed page metadata.
No infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CrawlSource:
    """Configuration for a single crawl source (URL, depth, crawler type, etc.)."""

    id: str
    url: str
    max_depth: int = 2
    crawler: str = "playwright"
    doc_only: bool = True
    seed_urls: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlResult:
    """A single crawled page (URL + HTML or content)."""

    url: str
    html: str
    source_id: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexedPage:
    """Metadata for a page that has been indexed (filename, chunk hashes, etc.)."""

    filename: str
    url: Optional[str]
    chunk_hashes: List[str]
    dirty: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


def crawl_source_from_dict(d: Dict[str, Any]) -> CrawlSource:
    """Build CrawlSource from a dict (e.g. config)."""
    return CrawlSource(
        id=d.get("id", ""),
        url=d.get("url", ""),
        max_depth=int(d.get("max_depth", 2)),
        crawler=d.get("crawler", "playwright"),
        doc_only=bool(d.get("doc_only", True)),
        seed_urls=list(d.get("seed_urls") or []),
        extra={k: v for k, v in d.items() if k not in ("id", "url", "max_depth", "crawler", "doc_only", "seed_urls")},
    )


__all__ = [
    "CrawlSource",
    "CrawlResult",
    "IndexedPage",
    "crawl_source_from_dict",
]
