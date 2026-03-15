"""
RAG search adapter: search a given collection by vector (for multi-collection merged context).
"""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


class QdrantRagSearchAdapter:
    """RagSearchPort implementation: search(collection_name, vector, top_k) via Qdrant HTTP API."""

    def __init__(self, base_url: str = "http://localhost:6333") -> None:
        self._url = base_url.rstrip("/")

    def search(
        self,
        collection_name: str,
        vector: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search collection by vector. Returns list of hits with id, score, payload."""
        if not httpx:
            return []
        try:
            resp = httpx.post(
                f"{self._url}/collections/{collection_name}/points/search",
                json={"vector": vector, "limit": top_k, "with_payload": True},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result") or []
        except Exception:
            return []


__all__ = ["QdrantRagSearchAdapter"]
