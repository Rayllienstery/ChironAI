"""
Playwright + CDP powered fetcher for Apple Developer documentation pages.

This module focuses purely on *fetching* and extracting the minimal raw
structured data we need for downstream Apple-specific parsing and
RAG-optimized markdown rendering.
"""

from __future__ import annotations

import asyncio
import contextlib
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
            # Apple docs can serve a generic portal/navigation page to bot-like clients.
            # Use a realistic UA and Accept-Language to increase chance of real content.
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Wait for the main title to appear.
            with contextlib.suppress(Exception):
                await page.wait_for_selector("main h1, article h1, h1", timeout=20000)
            # Wait for some real content (paragraph/code/section) to appear.
            try:
                await page.wait_for_selector(
                    "main p, main pre, main table, main h2, article p, article pre, article h2",
                    timeout=20000,
                )
            except Exception:
                # Apple SPA may keep long polling; a short settle still helps.
                await page.wait_for_timeout(2500)

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
                        const candidates = [
                          document.querySelector('main article'),
                          document.querySelector('article'),
                          document.querySelector('main'),
                          document.body,
                        ].filter(Boolean);

                        function score(el) {
                          const html = el.innerHTML || '';
                          const text = (el.textContent || '').trim();
                          const hasH1 = !!el.querySelector('h1');
                          const hasContent = !!el.querySelector('p, pre, table, h2, h3, li');
                          // Detect Apple Developer portal navigation patterns.
                          const portalHints = ['Stay Updated','Explore Platforms','Explore Technologies','Explore Community'];
                          const portalHits = portalHints.filter(h => text.includes(h)).length;
                          const listCount = el.querySelectorAll('li').length;
                          const linkCount = el.querySelectorAll('a').length;
                          let s = 0;
                          if (hasH1) s += 50;
                          if (hasContent) s += 30;
                          s += Math.min(40, Math.floor(text.length / 2000));
                          // Penalize portal-like pages: lots of nav lists/links + portal headings.
                          s -= portalHits * 40;
                          if (portalHits >= 2) s -= 80;
                          if (listCount > 200 && linkCount > 200) s -= 60;
                          return s;
                        }

                        let best = candidates[0];
                        let bestScore = score(best);
                        for (const el of candidates.slice(1)) {
                          const sc = score(el);
                          if (sc > bestScore) { best = el; bestScore = sc; }
                        }
                        return best ? best.innerHTML : (document.body ? document.body.innerHTML : '');
                    }"""
                )
            except Exception:  # noqa: BLE001
                body_html = ""

            # If we still got a portal/navigation page, do one retry after load.
            try:
                portal_markers = ("Stay Updated", "Explore Platforms", "Explore Technologies", "Explore Community")
                if body_html and sum(m in body_html for m in portal_markers) >= 2:
                    await page.goto(url, wait_until="load", timeout=60000)
                    await page.wait_for_timeout(2500)
                    retry_html = await page.evaluate(
                        """() => {
                            const el = document.querySelector('main article') || document.querySelector('article') || document.querySelector('main') || document.body;
                            return el ? el.innerHTML : (document.body ? document.body.innerHTML : '');
                        }"""
                    )
                    if retry_html and sum(m in retry_html for m in portal_markers) < sum(m in body_html for m in portal_markers):
                        body_html = retry_html
            except Exception:  # safe: portal retry optional; keep prior body_html
                pass

            # Hard guards for known bad targets: better to fail than to index portal navigation or stubs.
            try:
                path = (urlparse(url).path or "").rstrip("/")
                if (
                    path.endswith("/documentation/swiftui/observable")
                    and body_html
                    and sum(m in body_html for m in ("Stay Updated", "Explore Platforms")) >= 1
                ):
                    raise RuntimeError("Apple docs returned portal navigation page for swiftui/observable")
                if path.endswith("/documentation/swift/concurrency"):
                    # Reject near-empty landing pages (title-only stubs).
                    html = (body_html or "").strip()
                    has_real_blocks = any(tok in html for tok in ("<p", "<pre", "<code", "<table", "<h2", "<h3"))
                    if (len(html) < 1200) and (not has_real_blocks):
                        raise RuntimeError("Apple docs returned stub/low-signal page for swift/concurrency")
            except Exception:
                raise
        finally:
            with contextlib.suppress(Exception):
                await context.close()
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

