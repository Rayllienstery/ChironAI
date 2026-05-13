"""
Playwright + CDP powered fetcher for Apple Developer documentation pages.

This module focuses purely on *fetching* and extracting the minimal raw
structured data we need for downstream Apple-specific parsing and
RAG-optimized markdown rendering.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

from urllib.parse import urlparse

try:  # Optional dependency; caller must handle ImportError gracefully.
    from playwright.async_api import async_playwright  # type: ignore[import]

    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - environment without Playwright
    async_playwright = None  # type: ignore[assignment]
    _HAS_PLAYWRIGHT = False


@dataclass
class AppleDocRaw:
    """
    Minimal raw representation of an Apple Developer documentation page.

    This is intentionally low-level and close to what Playwright / CDP sees.
    Higher-level semantics (sections, blocks, metadata) are modeled in
    apple_docs_extract.AppleDocPage.
    """

    url: str
    initial_state: Optional[Dict[str, Any]]
    main_html: str
    title: Optional[str]
    breadcrumbs: list[str]


async def _fetch_apple_doc_raw_async(url: str) -> AppleDocRaw:
    """
    Fetch a single Apple documentation page via Playwright + CDP.

    Strategy:
    - Enforce https://developer.apple.com host (for now).
    - Load page with headless Chromium, wait for `networkidle`.
    - Grab:
      - document title;
      - `window.__INITIAL_STATE__` (if present);
      - innerHTML of <main> / <article> / <body>;
      - basic breadcrumbs text from the Apple docs breadcrumb nav.
    """
    if not _HAS_PLAYWRIGHT or async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install with "
            "`pip install playwright` and run `playwright install chromium`."
        )

    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url.lstrip("/")
        parsed = urlparse(url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Give Apple SPA some time to settle all XHR/fetch calls.
            await page.wait_for_load_state("networkidle", timeout=15000)

            # 1) document.title
            try:
                title: Optional[str] = await page.title()
            except Exception:  # noqa: BLE001
                title = None

            # 2) window.__INITIAL_STATE__ (Apple docs often expose JSON here).
            try:
                initial_state = await page.evaluate(
                    """() => {
                        try {
                            // Apple often keeps the doc payload under this key.
                            const s = (window as any).__INITIAL_STATE__;
                            if (!s) return null;
                            return s;
                        } catch {
                            return null;
                        }
                    }"""
                )
            except Exception:  # noqa: BLE001
                initial_state = None

            # 3) Breadcrumbs from Apple docs chrome.
            try:
                breadcrumbs: list[str] = await page.evaluate(
                    """() => {
                        const items = [];
                        // Try multiple selectors for Apple docs breadcrumbs
                        const nav = document.querySelector('nav[aria-label="Breadcrumbs"], nav[aria-label="Breadcrumb"], nav.breadcrumbs, nav[aria-label*="breadcrumb" i]');
                        if (nav) {
                            nav.querySelectorAll('a, span, li').forEach(el => {
                                const txt = (el.textContent || '').trim();
                                if (txt && txt.length > 0 && !items.includes(txt)) items.push(txt);
                            });
                        }
                        // Fallback: look for breadcrumb-like structure in main content
                        if (items.length === 0) {
                            const main = document.querySelector('main') || document.body;
                            const breadcrumbEls = main.querySelectorAll('ul li a, ol li a, nav a');
                            breadcrumbEls.forEach(el => {
                                const txt = (el.textContent || '').trim();
                                const href = el.getAttribute('href') || '';
                                // If it looks like a breadcrumb link (short text, links to parent sections)
                                if (txt && txt.length < 50 && (href.includes('/documentation/') || href.startsWith('/'))) {
                                    if (!items.includes(txt)) items.push(txt);
                                }
                            });
                        }
                        return items;
                    }"""
                )
            except Exception:  # noqa: BLE001
                breadcrumbs = []

            # 4) Inner HTML of the main content region.
            try:
                body_html = await page.evaluate(
                    """() => {
                        const main = document.querySelector('main') || document.querySelector('article') || document.body;
                        return main ? main.innerHTML : document.body.innerHTML;
                    }"""
                )
            except Exception:  # noqa: BLE001
                body_html = ""
        finally:
            await browser.close()

    main_html = f"<!DOCTYPE html><html><head></head><body>{body_html or ''}</body></html>"

    return AppleDocRaw(
        url=url,
        initial_state=initial_state if isinstance(initial_state, dict) else None,
        main_html=main_html,
        title=title,
        breadcrumbs=breadcrumbs,
    )


def fetch_apple_doc_raw(url: str) -> AppleDocRaw:
    """
    Synchronous wrapper around `_fetch_apple_doc_raw_async`.

    Intended for simple scripts (`app_tester.py`) and the crawl pipeline where
    we already run Playwright in an isolated async session per URL.
    """
    return asyncio.run(_fetch_apple_doc_raw_async(url))

