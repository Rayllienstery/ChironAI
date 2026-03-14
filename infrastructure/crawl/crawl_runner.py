"""
Crawl runner adapters implementing CrawlRunner.

PlaywrightCrawler is the only supported crawler; full implementation
remains in WebUI/app.py and can be invoked via a wrapper or migrated here later.
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


__all__ = ["PlaywrightCrawler"]
