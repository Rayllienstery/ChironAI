"""Shared crawler helpers used by WebUI routes."""

from __future__ import annotations

import re
from typing import Any


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


__all__ = ["build_source_meta", "is_safe_identifier", "normalize_seed_urls"]
