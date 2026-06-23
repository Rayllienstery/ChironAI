"""Minimal crawl page result."""


class CrawlResult:
    """url, success, html (fragment wrapped as full document)."""

    __slots__ = ("url", "success", "html")

    def __init__(self, url: str, success: bool, html: str = "") -> None:
        self.url = url
        self.success = success
        self.html = html


__all__ = ["CrawlResult"]
