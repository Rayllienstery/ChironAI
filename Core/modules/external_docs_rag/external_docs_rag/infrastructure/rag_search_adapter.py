"""
RAG search adapter: search a given collection by vector (for multi-collection merged context).
"""

from __future__ import annotations

from typing import Any

from rag_service.domain.errors import RetrievalError
from rag_service.infrastructure.qdrant_repository import QdrantRagRepository


class QdrantRagSearchAdapter:
    """RagSearchPort implementation delegating to canonical ``QdrantRagRepository``."""

    def __init__(self, base_url: str = "http://localhost:6333") -> None:
        self._base_url = base_url.rstrip("/")

    def search(
        self,
        collection_name: str,
        vector: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search collection by vector. Returns list of hits with id, score, payload."""
        repo = QdrantRagRepository(
            base_url=self._base_url,
            explicit_collection=collection_name,
        )
        try:
            return repo.search(vector, top_k)
        except RetrievalError:
            return []
        except Exception:
            return []


__all__ = ["QdrantRagSearchAdapter"]
