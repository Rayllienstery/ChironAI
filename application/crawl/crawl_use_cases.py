"""
Crawl and index application use cases.

Orchestrates crawl -> markdown store. Full crawl implementation lives in
WebUI/app.py; this module exposes a small use-case API for injection/testing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.entities.crawl import CrawlSource


def run_crawl_all_sources(
    sources: list[CrawlSource],
    crawl_fn: Callable[[str], Any],
    _markdown_store: Any,  # MarkdownStore - reserved for future wiring
) -> str:
    """
    Crawl all sources and update markdown store.
    crawl_fn(source_id) runs the crawl for that source (e.g. delegates to app.py).
    Returns a short status message.
    """
    for src in sources:
        crawl_fn(src.id)
    return f"Crawl requested for {len(sources)} sources."


__all__ = [
    "run_crawl_all_sources",
]
