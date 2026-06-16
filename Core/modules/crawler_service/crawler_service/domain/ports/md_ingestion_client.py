"""Port: push crawled content to md_ingestion_service (e.g. via HTTP)."""

from __future__ import annotations

from typing import Any, Protocol

from crawler_service.domain.entities import CrawlResult


class MdIngestionClient(Protocol):
    """Port for sending crawled content to md_ingestion_service."""

    def push_crawl_results(
        self,
        source_id: str,
        results: list[CrawlResult],
        collection: str,
    ) -> dict[str, Any]:
        """Push crawl results to ingestion. Returns summary (e.g. accepted, errors)."""
        ...


__all__ = ["MdIngestionClient"]
