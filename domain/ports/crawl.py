"""
Crawl runner port.

Abstract interface for running a crawler on a source.
Implementations (Playwright, crawl4ai) live in infrastructure.
"""

from __future__ import annotations

from typing import Protocol

from domain.entities.crawl import CrawlResult, CrawlSource


class CrawlRunner(Protocol):
    """Port for crawling a configured source."""

    def crawl(self, source: CrawlSource) -> list[CrawlResult]:
        """
        Crawl the given source and return list of results (URL + HTML/content).
        Raises domain.errors.CrawlError on failure.
        """
        ...


__all__ = ["CrawlRunner"]
