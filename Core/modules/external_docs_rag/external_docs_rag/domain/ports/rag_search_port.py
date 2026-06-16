"""Port for searching one collection by vector (used by build_merged_rag_context)."""

from __future__ import annotations

from typing import Any, Protocol


class RagSearchPort(Protocol):
    """Port for vector search in a single collection with given top_k."""

    def search(
        self,
        collection_name: str,
        vector: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        Search collection by vector. Returns list of hits with id, score, payload.
        """
        ...


__all__ = ["RagSearchPort"]
