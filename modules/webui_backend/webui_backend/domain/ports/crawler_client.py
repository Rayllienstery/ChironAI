"""Port: call crawler_service via HTTP (core/contracts/crawler_api)."""

from __future__ import annotations

from typing import Any, Protocol


class CrawlerClient(Protocol):
    """Port for crawler service."""

    def list_sources(self) -> dict[str, Any]:
        """GET /crawl/sources."""
        ...

    def start_crawl(self, source_id: str) -> dict[str, Any]:
        """POST /crawl/start with source_id."""
        ...


__all__ = ["CrawlerClient"]
