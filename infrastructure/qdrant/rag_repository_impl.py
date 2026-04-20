"""
Qdrant RAG repository implementing RagRepository.

Uses HTTP API for search and hybrid query. Maps httpx errors to domain.errors.RetrievalError.
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

    DENSE_NAME = "dense"
    SPARSE_NAME = "sparse"
    LEGACY_DENSE_FALLBACK_ENV = "QDRANT_LEGACY_DENSE_FALLBACK_ENABLED"

    def __init__(
        self,
        base_url: str | None = None,
        collection_file: str | None = None,
        default_collection: str = "webcrawl",
        explicit_collection: str | None = None,
    ) -> None:
        self._url = (base_url or get_qdrant_url()).rstrip("/")
        self._collection_file = collection_file
        self._default_collection = default_collection
        self._explicit_collection = (explicit_collection or "").strip() or None
        self._mode_cache_coll: str | None = None
        self._mode_cache: str | None = None  # "legacy" | "named_dense" | "hybrid"

    def _legacy_dense_fallback_enabled(self) -> bool:
        raw = (os.getenv(self.LEGACY_DENSE_FALLBACK_ENV) or "1").strip().lower()
        return raw in ("1", "true", "yes", "on")

    def get_collection_name(self) -> str:
        """Return current collection name. Explicit collection overrides file and default."""
        if self._explicit_collection:
            return self._explicit_collection
        if self._collection_file and os.path.isfile(self._collection_file):
            try:
                with open(self._collection_file, encoding="utf-8") as f:
                    name = f.read().strip()
                if name:
                    return name
            except OSError:
                pass
        return self._default_collection

    def _collection_vector_mode(self) -> str:
        """Return 'legacy' (single unnamed vector) or 'hybrid' (dense + sparse names)."""
        coll = self.get_collection_name()
        if self._mode_cache_coll == coll and self._mode_cache is not None:
            return self._mode_cache
        mode = "legacy"
        try:
            resp = httpx.get(f"{self._url}/collections/{coll}", timeout=10)
            resp.raise_for_status()
            data = resp.json().get("result") or {}
            params = (data.get("config") or {}).get("params") or {}
            sparse = params.get("sparse_vectors") or {}
            vectors = params.get("vectors")
            if isinstance(sparse, dict) and len(sparse) > 0:
                mode = "hybrid"
            elif isinstance(vectors, dict) and self.DENSE_NAME in vectors:
                # Named dense without sparse (partial); still use named dense search
                mode = "named_dense"
            else:
                mode = "legacy"
        except Exception:
            mode = "legacy"
        self._mode_cache_coll = coll
        self._mode_cache = mode
        return mode

    def supports_hybrid(self) -> bool:
        return self._collection_vector_mode() == "hybrid"

    def search(
        self,
        vector: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None = None,
        *,
        sparse_indices: list[int] | None = None,
        sparse_values: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Search: hybrid RRF when sparse vectors exist and indices provided; else dense-only."""
        coll = self.get_collection_name()
        mode = self._collection_vector_mode()
        use_hybrid = (
            mode == "hybrid"
            and sparse_indices
            and sparse_values
            and len(sparse_indices) == len(sparse_values)
        )
        if use_hybrid:
            return self._search_hybrid(
                coll,
                vector,
                sparse_indices,
                sparse_values,
                top_k,
                filter_dict,
            )
        return self._search_dense_only(coll, vector, top_k, filter_dict, mode)

    def _search_dense_only(
        self,
        coll: str,
        vector: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None,
        mode: str,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "limit": top_k,
            "with_payload": True,
        }
        if mode in ("hybrid", "named_dense"):
            body["vector"] = {"name": self.DENSE_NAME, "vector": vector}
        else:
            body["vector"] = vector
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
            # Explicit compatibility policy: only fallback to unnamed dense when enabled.
            if mode in ("hybrid", "named_dense") and self._legacy_dense_fallback_enabled():
                try:
                    body2 = {"vector": vector, "limit": top_k, "with_payload": True}
                    if filter_dict:
                        body2["filter"] = filter_dict
                    resp2 = httpx.post(
                        f"{self._url}/collections/{coll}/points/search",
                        json=body2,
                        timeout=30,
                    )
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    return data2.get("result") or []
                except Exception:
                    pass
            raise RetrievalError(
                f"Qdrant search error (collection={coll}): {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise RetrievalError(f"Qdrant request error: {e}") from e

    def _search_hybrid(
        self,
        coll: str,
        dense: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        prefetch_limit = max(top_k * 3, top_k)
        body: dict[str, Any] = {
            "prefetch": [
                {
                    "query": dense,
                    "using": self.DENSE_NAME,
                    "limit": prefetch_limit,
                },
                {
                    "query": {"indices": sparse_indices, "values": sparse_values},
                    "using": self.SPARSE_NAME,
                    "limit": prefetch_limit,
                },
            ],
            "query": {"fusion": "rrf"},
            "limit": top_k,
            "with_payload": True,
        }
        if filter_dict:
            body["filter"] = filter_dict
        try:
            resp = httpx.post(
                f"{self._url}/collections/{coll}/points/query",
                json=body,
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("result")
            points: list[Any] = []
            if isinstance(raw, dict):
                points = raw.get("points") or []
            elif isinstance(raw, list):
                points = raw
            if points and isinstance(points[0], dict):
                return [
                    {
                        "id": p.get("id"),
                        "score": float(p.get("score") or 0.0),
                        "payload": p.get("payload") or {},
                    }
                    for p in points
                ]
            return []
        except httpx.HTTPStatusError:
            return self._search_dense_only(coll, dense, top_k, filter_dict, "hybrid")
        except httpx.RequestError as e:
            raise RetrievalError(f"Qdrant hybrid query error: {e}") from e


__all__ = ["QdrantRagRepository"]
