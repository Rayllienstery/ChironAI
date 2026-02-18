"""
Crawl runner adapters implementing CrawlRunner.

PlaywrightCrawler and Crawl4AICrawler are intended to be implemented by
extracting logic from WebUI/app.py. This module provides the protocol
satisfaction; full implementation can remain in app.py and be invoked
via a wrapper or migrated here later.
"""

from __future__ import annotations

from typing import List

from domain.entities.crawl import CrawlResult, CrawlSource


class PlaywrightCrawler:
    """Crawl runner using Playwright. Implement by delegating to app crawl or migrate here."""

    def crawl(self, source: CrawlSource) -> List[CrawlResult]:
        """Crawl the source. Raises CrawlError on failure."""
        raise NotImplementedError(
            "PlaywrightCrawler: use WebUI app.py crawl flow or implement by extracting from app.py"
        )


class Crawl4AICrawler:
    """Crawl runner using crawl4ai. Implement by delegating to app crawl or migrate here."""

    def crawl(self, source: CrawlSource) -> List[CrawlResult]:
        """Crawl the source. Raises CrawlError on failure."""
        raise NotImplementedError(
            "Crawl4AICrawler: use WebUI app.py crawl flow or implement by extracting from app.py"
        )


__all__ = ["PlaywrightCrawler", "Crawl4AICrawler"]
