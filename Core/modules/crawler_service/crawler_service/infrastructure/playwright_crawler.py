"""Playwright-based crawl runner implementing CrawlRunner port (fetch-only, no FS write)."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from crawler_service.crawler_settings import load_crawler_runtime_config
from crawler_service.domain import entities as entities_mod
from crawler_service.infrastructure.crawl_result import CrawlResult as PageFetchResult
from crawler_service.infrastructure.playwright_deep_crawl import run_async_crawl_playwright
from crawler_service.paths import default_project_root


class PlaywrightCrawler:
    """BFS Playwright crawl; returns domain CrawlResult rows (WWDC sources yield [])."""

    def crawl(self, source: entities_mod.CrawlSource) -> list[entities_mod.CrawlResult]:
        if (source.extra or {}).get("type") == "wwdc_transcripts":
            return []
        if source.crawler != "playwright":
            return []

        project_root = default_project_root()
        runtime = load_crawler_runtime_config(project_root)
        start_url = source.url
        max_depth = source.max_depth
        start_parsed = urlparse(start_url)
        start_path = (start_parsed.path or "").strip("/")
        start_segments = [s for s in start_path.split("/") if s]
        allowed_prefix = "/" + "/".join(start_segments[:2]) + "/" if start_segments else "/"
        doc_only = source.doc_only
        ex = source.extra or {}
        effective_path_prefixes = ex.get("path_prefixes") or runtime.framework_root_prefixes
        effective_excluded = ex.get("excluded_path_substrings") or runtime.excluded_path_substrings

        logs: list[str] = []

        def log(msg: str) -> None:
            logs.append(msg)

        results = asyncio.run(
            run_async_crawl_playwright(
                start_url,
                max_depth,
                allowed_prefix,
                doc_only,
                runtime,
                log,
                extra_seed_urls=source.seed_urls or None,
                on_page_processed=None,
                allowed_path_prefixes=effective_path_prefixes,
                excluded_path_substrings=effective_excluded,
            )
        )
        out: list[entities_mod.CrawlResult] = []
        for r in results:
            if not isinstance(r, PageFetchResult) or not r.success:
                continue
            out.append(
                entities_mod.CrawlResult(
                    url=r.url,
                    html=r.html or "",
                    source_id=source.id,
                )
            )
        return out


__all__ = ["PlaywrightCrawler"]
