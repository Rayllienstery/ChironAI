"""
Web crawling infrastructure.

Provides Playwright-based CrawlRunner; full crawl logic remains in WebUI/app.py until migrated.
"""

from infrastructure.crawl.crawl_runner import PlaywrightCrawler

__all__ = ["PlaywrightCrawler"]
