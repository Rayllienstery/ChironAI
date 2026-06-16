"""
Crawl runner adapters implementing CrawlRunner.

PlaywrightCrawler is the only supported crawler; full implementation
remains in crawler_service/webui_backend and can be invoked via a wrapper or migrated here later.
"""

from __future__ import annotations

from typing import List

from domain.entities.crawl import CrawlResult, CrawlSource


class PlaywrightCrawler:
    """Crawl runner using Playwright. Implement by delegating to app crawl or migrate here."""

    def crawl(self, source: CrawlSource) -> List[CrawlResult]:
        """Crawl the source. Raises CrawlError on failure."""
        raise NotImplementedError(
            "PlaywrightCrawler: use crawler_service crawl flow or implement it here"
        )


__all__ = ["PlaywrightCrawler"]
