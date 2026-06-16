"""Run sync Apple doc fetch off the asyncio loop when needed."""

from __future__ import annotations

import asyncio
import concurrent.futures

_executor: concurrent.futures.ThreadPoolExecutor | None = None


def fetch_apple_doc_raw_safe(fetch_fn, url: str):
    """Call fetch_fn(url); if inside running event loop, run fetch in a thread."""
    global _executor
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fetch_fn(url)
    if _executor is None:
        _executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    return _executor.submit(fetch_fn, url).result()
