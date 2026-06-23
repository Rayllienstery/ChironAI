"""Crawler use cases: run crawl and push to md_ingestion."""

from __future__ import annotations

from typing import Any

from crawler_service.domain.entities import CrawlSource
from crawler_service.domain.ports import CrawlRunner, MdIngestionClient


def run_crawl_source(
    source: CrawlSource,
    crawl_runner: CrawlRunner,
    md_ingestion_client: MdIngestionClient,
    collection: str,
) -> dict[str, Any]:
    """Crawl one source and push results to md_ingestion. Returns summary."""
    results = crawl_runner.crawl(source)
    return md_ingestion_client.push_crawl_results(source.id, results, collection)


def run_crawl_all_sources(
    sources: list[CrawlSource],
    crawl_runner: CrawlRunner,
    md_ingestion_client: MdIngestionClient,
    collection: str,
) -> list[dict[str, Any]]:
    """Crawl all sources and push each to md_ingestion. Returns list of summaries."""
    out = []
    for src in sources:
        out.append(run_crawl_source(src, crawl_runner, md_ingestion_client, collection))
    return out


__all__ = ["run_crawl_source", "run_crawl_all_sources"]
