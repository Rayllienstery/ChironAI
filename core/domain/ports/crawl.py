"""
Crawl runner port.

Abstract interface for running a crawler on a source.
Playwright implementation lives in infrastructure.
"""

from __future__ import annotations

from typing import Protocol

from domain.entities.crawl import CrawlResult, CrawlSource


class CrawlRunner(Protocol):
    """Port for crawling a configured source."""

    def crawl(self, source: CrawlSource) -> list[CrawlResult]:
        """Crawl the given source and return its results.

        Args:
            source: The crawl source to process (URL, depth, include/exclude rules).

        Returns:
            A list of crawl results, each carrying the URL and normalized content.

        Raises:
            domain.errors.CrawlError: If the crawler fails irrecoverably.
        """
        ...


__all__ = ["CrawlRunner"]
