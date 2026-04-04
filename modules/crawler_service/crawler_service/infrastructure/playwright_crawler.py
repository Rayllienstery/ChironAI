"""Playwright-based crawler. Stub: full implementation can be migrated from WebUI/app.py."""

from __future__ import annotations

from crawler_service.domain.entities import CrawlResult, CrawlSource


class PlaywrightCrawler:
    """Crawl runner using Playwright. Implement by delegating to WebUI app or migrate here."""

    def crawl(self, source: CrawlSource) -> list[CrawlResult]:
        raise NotImplementedError(
            "PlaywrightCrawler: implement by extracting from WebUI/app.py or delegate to app crawl"
        )


__all__ = ["PlaywrightCrawler"]
