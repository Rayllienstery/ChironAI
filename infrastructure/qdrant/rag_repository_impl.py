"""
Qdrant RAG repository implementing RagRepository.

Uses HTTP API for search. Maps httpx/requests errors to domain.errors.RetrievalError.
Collection name is read from a file (e.g. last_collection.txt) or default.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from domain.errors import RetrievalError

try:
    from config import get_qdrant_url
except ImportError:
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore


class QdrantRagRepository:
    """RAG repository using Qdrant HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        collection_file: str | None = None,
        default_collection: str = "webcrawl",
    ) -> None:
        self._url = (base_url or get_qdrant_url()).rstrip("/")
        self._collection_file = collection_file
        self._default_collection = default_collection

    def get_collection_name(self) -> str:
        """Return current collection name (from file or default)."""
        if self._collection_file and os.path.isfile(self._collection_file):
            try:
                with open(self._collection_file, encoding="utf-8") as f:
                    name = f.read().strip()
                if name:
                    return name
            except Exception:
                pass
        return self._default_collection

    def search(
        self,
        vector: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar points. Returns list of hits with id, score, payload."""
        coll = self.get_collection_name()
        body: dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": True,
        }
        if filter_dict:
            body["filter"] = filter_dict
        try:
            resp = httpx.post(
                f"{self._url}/collections/{coll}/points/search",
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result") or []
        except httpx.HTTPStatusError as e:
            raise RetrievalError(
                f"Qdrant search error (collection={coll}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise RetrievalError(f"Qdrant request error: {e}") from e


__all__ = ["QdrantRagRepository"]
