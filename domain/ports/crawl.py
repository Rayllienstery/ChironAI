"""
Crawl runner port.

Abstract interface for running a crawler on a source.
Implementations (Playwright, crawl4ai) live in infrastructure.
"""

from __future__ import annotations

from typing import List, Protocol

from domain.entities.crawl import CrawlSource, CrawlResult


class CrawlRunner(Protocol):
    """Port for crawling a configured source."""

    def crawl(self, source: CrawlSource) -> List[CrawlResult]:
        """
        Crawl the given source and return list of results (URL + HTML/content).
        Raises domain.errors.CrawlError on failure.
        """
        ...


__all__ = ["CrawlRunner"]
