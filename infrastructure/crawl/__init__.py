"""
Web crawling infrastructure.

Provides Playwright-based CrawlRunner; full crawl logic remains in crawler_service/webui_backend until migrated.
"""

from infrastructure.crawl.crawl_runner import PlaywrightCrawler

__all__ = ["PlaywrightCrawler"]
