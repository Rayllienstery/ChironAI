"""Tests for crawler source stats helper."""

from __future__ import annotations

from api.http.webui_crawler_helpers import compute_source_stats


def test_compute_source_stats_counts_indexed_pages() -> None:
    meta = {
        "last_crawled": "2026-01-01",
        "pages": {
            "a": {"chunk_hashes": ["h1"]},
            "b": {"chunk_hashes": []},
            "c": {},
        },
    }
    stats = compute_source_stats(meta)
    assert stats["total_pages"] == 3
    assert stats["indexed_pages"] == 1
    assert stats["last_crawled"] == "2026-01-01"
