"""
RAG collection freshness for TTL-based refresh.

Given collection metadata (last_refreshed_at) and TTL in days,
returns whether the collection is fresh, missing, or stale.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

FreshnessStatus = Literal["fresh", "no_record", "stale"]


def check_collection_freshness(
    meta: dict[str, str] | None,
    ttl_days: int,
) -> FreshnessStatus:
    """
    Check if a collection is fresh (within TTL), has no record, or is stale.

    Args:
        meta: From get_collection_meta (collection_name, framework_id, version, last_refreshed_at).
              None if no record.
        ttl_days: Number of days after last_refreshed_at the collection is considered fresh.

    Returns:
        "no_record" if meta is None, "stale" if last_refreshed_at is older than ttl_days, "fresh" otherwise.
    """
    if meta is None:
        return "no_record"
    raw = meta.get("last_refreshed_at") or ""
    if not raw:
        return "no_record"
    try:
        # Support ISO format with or without Z
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "stale"
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return "fresh" if dt >= cutoff else "stale"
