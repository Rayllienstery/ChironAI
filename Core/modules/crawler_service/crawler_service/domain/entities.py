"""Domain entities for crawling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrawlSource:
    """Configuration for a single crawl source."""

    id: str
    url: str
    max_depth: int = 2
    crawler: str = "playwright"
    doc_only: bool = True
    seed_urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlResult:
    """A single crawled page (URL + content)."""

    url: str
    html: str
    source_id: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlStatus:
    """Status of a crawl job."""

    job_id: str
    status: str  # "pending" | "running" | "done" | "failed"
    sources_crawled: int = 0
    pages: int = 0
    error: str | None = None


def crawl_source_from_dict(d: dict[str, Any]) -> CrawlSource:
    """Build CrawlSource from config dict."""
    return CrawlSource(
        id=d.get("id", ""),
        url=d.get("url", ""),
        max_depth=int(d.get("max_depth", 2)),
        crawler=d.get("crawler", "playwright"),
        doc_only=bool(d.get("doc_only", True)),
        seed_urls=list(d.get("seed_urls") or []),
        extra={k: v for k, v in d.items() if k not in ("id", "url", "max_depth", "crawler", "doc_only", "seed_urls")},
    )


__all__ = ["CrawlSource", "CrawlResult", "CrawlStatus", "crawl_source_from_dict"]
