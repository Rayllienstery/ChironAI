"""
Crawl and index application use cases.

Orchestrates crawl -> markdown store -> index. For full implementation
the actual crawl/index logic remains in WebUI/app.py; this module exposes
the use-case API so CLI can call it with injected dependencies.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from domain.entities.crawl import CrawlSource


def run_crawl_all_sources(
    sources: List[CrawlSource],
    crawl_fn: Callable[[str], Any],
    markdown_store: Any,
) -> str:
    """
    Crawl all sources and update markdown store.
    crawl_fn(source_id) runs the crawl for that source (e.g. delegates to app.py).
    Returns a short status message.
    """
    for src in sources:
        crawl_fn(src.id)
    return f"Crawl requested for {len(sources)} sources."


def run_index_all_sources(
    sources: List[str],
    index_fn: Callable[..., Any],
    dry_run: bool = False,
    force_reindex_chunks: bool = False,
) -> str:
    """
    Index markdown from all sources into the vector store.
    index_fn(incremental, dry_run, force_reindex_chunks) performs the index (e.g. app.index_markdown).
    """
    index_fn(incremental=True, dry_run=dry_run, force_reindex_chunks=force_reindex_chunks)
    return "Index completed."


def run_rebuild_all(
    rebuild_fn: Callable[[bool], Any],
    dry_run: bool = False,
) -> str:
    """
    Rebuild vector collection from scratch.
    rebuild_fn(dry_run) performs the rebuild (e.g. app.rebuild_all).
    """
    rebuild_fn(dry_run=dry_run)
    return "Rebuild completed."


__all__ = [
    "run_crawl_all_sources",
    "run_index_all_sources",
    "run_rebuild_all",
]
