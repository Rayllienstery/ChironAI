"""Tests for crawler source stats helper."""

from __future__ import annotations

from api.http.webui_crawler_helpers import (
    build_source_meta,
    compute_source_stats,
    is_safe_identifier,
    normalize_seed_urls,
)


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


def test_normalize_seed_urls_filters_empty_values() -> None:
    assert normalize_seed_urls([" https://a ", "", None, "https://b"]) == [
        "https://a",
        "https://b",
    ]
    assert normalize_seed_urls("not-a-list") == []


def test_is_safe_identifier_accepts_url_safe_ids() -> None:
    assert is_safe_identifier("apple_docs")
    assert is_safe_identifier("wwdc-2025")
    assert not is_safe_identifier("../escape")
    assert not is_safe_identifier("has space")


def test_build_source_meta_persists_defaults() -> None:
    meta = build_source_meta(
        source_id="docs",
        url="https://example.com",
        max_depth=2,
        crawler="playwright",
        doc_only=True,
        seed_urls=["https://example.com/start"],
    )
    assert meta["source_id"] == "docs"
    assert meta["seed_urls"] == ["https://example.com/start"]
    assert meta["pages"] == {}
