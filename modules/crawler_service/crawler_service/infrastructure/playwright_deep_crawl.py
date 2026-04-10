"""Playwright-based BFS crawl."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from crawler_service.constants import (
    CRAWL_BACKOFF_BASE_SEC,
    CRAWL_BACKOFF_MAX_SEC,
    CRAWL_CONCURRENCY,
    CRAWL_DOM_READY_WAIT_MS,
    CRAWL_GOTO_TIMEOUT_MS,
    CRAWL_MAX_RETRIES_429,
)
from crawler_service.crawler_settings import CrawlerRuntimeConfig
from crawler_service.domain.url_rules import crawl_url_allowed, link_passes_filters
from crawler_service.infrastructure.crawl_result import CrawlResult

if TYPE_CHECKING:
    pass

try:
    from playwright.async_api import async_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None  # type: ignore[assignment,misc]
    _HAS_PLAYWRIGHT = False


async def fetch_one_url(
    browser: Any,
    url: str,
    depth: int,
    semaphore: asyncio.Semaphore,
    base_url: str,
    start_parsed: Any,
    prefix_p: str,
    doc_only: bool,
    log: Callable[[str], None],
) -> tuple[CrawlResult, list[str]]:
    """Single goto per URL; returns (result, absolute link URLs)."""
    async with semaphore:
        for attempt in range(CRAWL_MAX_RETRIES_429):
            page = None
            try:
                page = await browser.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=CRAWL_GOTO_TIMEOUT_MS,
                )
                if response and response.status == 429:
                    retry_after = response.headers.get("retry-after", "").strip()
                    wait_sec = CRAWL_BACKOFF_MAX_SEC
                    if retry_after.isdigit():
                        wait_sec = min(int(retry_after), CRAWL_BACKOFF_MAX_SEC)
                    else:
                        wait_sec = min(
                            CRAWL_BACKOFF_BASE_SEC**attempt,
                            CRAWL_BACKOFF_MAX_SEC,
                        )
                    await page.close()
                    page = None
                    log(
                        f"  WARNING: 429 for {url}, retry in {wait_sec}s "
                        f"(attempt {attempt + 1}/{CRAWL_MAX_RETRIES_429})"
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                break
            except Exception:
                if page:
                    await page.close()
                if attempt + 1 >= CRAWL_MAX_RETRIES_429:
                    return CrawlResult(url, False, ""), []
                await asyncio.sleep(min(CRAWL_BACKOFF_BASE_SEC**attempt, CRAWL_BACKOFF_MAX_SEC))
                continue

        if not page:
            return CrawlResult(url, False, ""), []

        try:
            await asyncio.sleep(CRAWL_DOM_READY_WAIT_MS / 1000.0)
        except Exception:
            pass

        try:
            body = await page.evaluate("""() => {
                const main = document.querySelector('main') || document.querySelector('article') || document.body;
                return main ? main.innerHTML : document.body.innerHTML;
            }""")
        except Exception:
            body = ""
        try:
            links = await page.evaluate("""() => {
                const seen = new Set();
                const out = [];
                function add(h) {
                    if (h && (h.startsWith('http') || h.startsWith('/')) && !seen.has(h)) {
                        seen.add(h);
                        out.push(h);
                    }
                }
                [document.querySelector('main'), document.querySelector('aside'), document.querySelector('nav')]
                    .filter(Boolean).forEach(root => {
                        if (root) root.querySelectorAll('a[href]').forEach(a => add(a.getAttribute('href')));
                    });
                document.querySelectorAll('a[href]').forEach(a => add(a.getAttribute('href')));
                return out;
            }""")
        except Exception:
            links = []
        await page.close()

        if not body:
            return CrawlResult(url, False, ""), links if isinstance(links, list) else []

        full_html = f"<!DOCTYPE html><html><head></head><body>{body}</body></html>"
        result = CrawlResult(url, True, full_html)

        absolute_links: list[str] = []
        for raw in (links if isinstance(links, list) else []):
            href = (raw or "").split("#")[0].strip()
            if not href:
                continue
            if href.startswith("//"):
                next_url = f"{start_parsed.scheme}:{href}"
            elif href.startswith("/"):
                next_url = f"{base_url.rstrip('/')}{href}"
            elif href.startswith("http"):
                next_url = href
            else:
                continue
            absolute_links.append(next_url)

        return result, absolute_links


async def run_async_crawl_playwright(
    start_url: str,
    max_depth: int,
    allowed_prefix: str,
    doc_only: bool,
    runtime: CrawlerRuntimeConfig,
    log: Callable[[str], None],
    extra_seed_urls: list[str] | None = None,
    on_page_processed: Callable[[CrawlResult], None] | None = None,
    allowed_path_prefixes: list[str] | None = None,
    excluded_path_substrings: list[str] | None = None,
) -> list[CrawlResult]:
    """BFS crawl using Playwright."""
    if not _HAS_PLAYWRIGHT or async_playwright is None:
        log("WARNING: Playwright not installed; run: pip install playwright && playwright install chromium")
        return []
    start_parsed = urlparse(start_url)
    base_url = f"{start_parsed.scheme or 'https'}://{start_parsed.netloc}"
    visited: set[str] = set()
    results: list[CrawlResult] = []
    queue: list[tuple[str, int]] = [(start_url, 0)]
    for u in extra_seed_urls or []:
        u = (u or "").strip()
        if u and u != start_url:
            queue.append((u, 0))
    prefix_p = allowed_prefix.rstrip("/")
    semaphore = asyncio.Semaphore(CRAWL_CONCURRENCY)
    excluded_eff = (
        excluded_path_substrings if excluded_path_substrings is not None else runtime.excluded_path_substrings
    )
    path_roots = allowed_path_prefixes if allowed_path_prefixes is not None else runtime.framework_root_prefixes

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            while queue:
                batch: list[tuple[str, int]] = []
                while len(batch) < CRAWL_CONCURRENCY and queue:
                    url, depth = queue.pop(0)
                    if not crawl_url_allowed(
                        url,
                        depth,
                        max_depth,
                        start_parsed,
                        base_url,
                        prefix_p,
                        doc_only,
                        visited,
                        path_roots=path_roots,
                        excluded_substrings=excluded_eff,
                    ):
                        continue
                    visited.add(url)
                    batch.append((url, depth))

                if not batch:
                    continue

                for url, depth in batch:
                    log(f"  Fetching [depth {depth}]: {url}")

                tasks = [
                    fetch_one_url(
                        browser, url, depth, semaphore, base_url, start_parsed, prefix_p, doc_only, log
                    )
                    for url, depth in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for (url, depth), outcome in zip(batch, batch_results):
                    if isinstance(outcome, BaseException):
                        results.append(CrawlResult(url, False, ""))
                        if on_page_processed:
                            on_page_processed(CrawlResult(url, False, ""))
                        continue
                    result, absolute_links = outcome
                    results.append(result)
                    if on_page_processed:
                        on_page_processed(result)
                    if depth >= max_depth:
                        continue
                    for next_url in absolute_links:
                        if link_passes_filters(
                            next_url,
                            start_parsed,
                            prefix_p,
                            doc_only,
                            path_roots=path_roots,
                            excluded_substrings=excluded_eff,
                        ):
                            if next_url not in visited:
                                queue.append((next_url, depth + 1))
        finally:
            await browser.close()
    return results


__all__ = ["run_async_crawl_playwright", "fetch_one_url"]
