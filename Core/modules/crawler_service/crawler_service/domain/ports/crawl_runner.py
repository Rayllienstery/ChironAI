"""Crawl runner port: run crawler on a source."""

from __future__ import annotations

from typing import Protocol

from crawler_service.domain.entities import CrawlResult, CrawlSource


class CrawlRunner(Protocol):
    """Port for crawling a configured source."""

    def crawl(self, source: CrawlSource) -> list[CrawlResult]:
        """Crawl the source and return results. Raises CrawlError on failure."""
        ...


__all__ = ["CrawlRunner"]
