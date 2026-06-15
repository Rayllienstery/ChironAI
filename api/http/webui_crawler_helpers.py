"""Shared crawler helpers used by WebUI routes."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from webui_backend.paths import webui_data_dir

_WEBUI_LOG = logging.getLogger("webui")

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def normalize_seed_urls(raw_values: object) -> list[str]:
    """Return trimmed non-empty seed URLs from an arbitrary JSON value."""
    if not isinstance(raw_values, list):
        return []
    return [str(value).strip() for value in raw_values if str(value or "").strip()]


def is_safe_identifier(value: str) -> bool:
    """True when the identifier is limited to URL/path-safe alnum, underscore, hyphen."""
    return bool(_SAFE_IDENTIFIER_RE.match((value or "").strip()))


def build_source_meta(
    *,
    source_id: str,
    url: str,
    max_depth: int,
    crawler: str,
    doc_only: bool,
    seed_urls: list[str],
) -> dict[str, Any]:
    """Build the persisted crawler source metadata document."""
    return {
        "source_id": source_id,
        "source_url": url,
        "max_depth": max_depth,
        "crawler": crawler,
        "doc_only": doc_only,
        "seed_urls": seed_urls,
        "last_crawled": None,
        "hash_algo": "sha256",
        "pages": {},
    }


def compute_source_stats(meta: dict[str, Any]) -> dict[str, Any]:
    """Calculate page/index statistics from a source meta document."""
    pages = meta.get("pages", {})
    if not isinstance(pages, dict):
        pages = {}
    total_pages = len(pages)
    indexed_pages = sum(
        1
        for p in pages.values()
        if isinstance(p, dict) and p.get("chunk_hashes") and len(p.get("chunk_hashes", [])) > 0
    )
    return {
        "total_pages": total_pages,
        "indexed_pages": indexed_pages,
        "last_crawled": meta.get("last_crawled"),
    }


def get_crawler_sources_dir() -> str:
    """Path to WebUI/rag_sources directory."""
    return str(webui_data_dir() / "rag_sources")


def load_source_meta(source_id: str) -> dict[str, Any] | None:
    """Load meta.json for a source. Returns None if not found."""
    sources_dir = get_crawler_sources_dir()
    meta_path = os.path.join(sources_dir, source_id, "meta.json")
    if not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("source_id", source_id)
        data.setdefault("source_url", "")
        data.setdefault("last_crawled", None)
        data.setdefault("hash_algo", "sha256")
        data.setdefault("pages", {})
        return data
    except Exception as e:
        _WEBUI_LOG.warning("Failed to load meta.json for %s: %s", source_id, e)
        return None


def discover_crawler_sources() -> list[str]:
    """Scan WebUI/rag_sources directory to find all source IDs."""
    sources_dir = get_crawler_sources_dir()
    if not os.path.isdir(sources_dir):
        return []
    source_ids: list[str] = []
    for item in os.listdir(sources_dir):
        item_path = os.path.join(sources_dir, item)
        if os.path.isdir(item_path):
            meta_path = os.path.join(item_path, "meta.json")
            if os.path.isfile(meta_path):
                source_ids.append(item)
    return sorted(source_ids)


__all__ = [
    "build_source_meta",
    "compute_source_stats",
    "discover_crawler_sources",
    "get_crawler_sources_dir",
    "is_safe_identifier",
    "load_source_meta",
    "normalize_seed_urls",
]
