"""List Qdrant collection names via the HTTP API."""

from __future__ import annotations

import requests

try:
    from config import get_qdrant_url
except ImportError:
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment,misc]


def list_collection_names(*, timeout_sec: float = 5.0) -> list[str]:
    """Return Qdrant collection names (empty when unreachable or on error)."""
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=timeout_sec)
        if not resp.ok:
            return []
        data = resp.json() or {}
        raw = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw:
            if isinstance(col, dict):
                name = col.get("name")
            else:
                name = str(col)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


__all__ = ["list_collection_names"]
