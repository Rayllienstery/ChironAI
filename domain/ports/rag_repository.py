"""
RAG repository port.

Abstract interface for vector search over indexed chunks.
Implementations (e.g. Qdrant) live in infrastructure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class RagRepository(Protocol):
    """Port for searching and reading from the RAG vector store."""

    def get_collection_name(self) -> str:
        """Return the current collection name (e.g. from last crawl or default)."""
        ...

    def search(
        self,
        vector: List[float],
        top_k: int,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar points by vector.
        Returns list of hits with "id", "score", "payload" (at least "text").
        """
        ...


__all__ = ["RagRepository"]
