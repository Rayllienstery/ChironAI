"""
Domain entities for crawling and indexing.

Minimal data structures for crawl sources, results, and indexed page metadata.
No infrastructure dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, cast


@dataclass
class CrawlSource:
    """Configuration for a single crawl source (URL, depth, crawler type, etc.)."""

    id: str
    url: str
    max_depth: int = 2
    crawler: str = "playwright"
    doc_only: bool = True
    seed_urls: list[str] = field(default_factory=lambda: cast(list[str], []))
    extra: dict[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))


@dataclass
class CrawlResult:
    """A single crawled page (URL + HTML or content)."""

    url: str
    html: str
    source_id: str
    extra: dict[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))


@dataclass
class IndexedPage:
    """Metadata for a page that has been indexed (filename, chunk hashes, etc.)."""

    filename: str
    url: Optional[str]
    chunk_hashes: list[str]
    extra: dict[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))


def crawl_source_from_dict(d: dict[str, Any]) -> CrawlSource:
    """Build CrawlSource from a dictionary.

    Args:
        d: A dictionary containing crawl source configuration (id, url, etc.).

    Returns:
        A CrawlSource entity populated from the dictionary.
    """
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
