"""
Web crawling infrastructure.

Provides concrete CrawlRunner implementations based on Playwright and
crawl4ai. Full crawl logic may remain in WebUI/app.py until migrated.
"""

from infrastructure.crawl.crawl_runner import Crawl4AICrawler, PlaywrightCrawler

__all__ = ["Crawl4AICrawler", "PlaywrightCrawler"]
