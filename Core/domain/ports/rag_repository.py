"""
RAG repository port.

Abstract interface for vector search over indexed chunks.
Implementations (e.g. Qdrant) live in infrastructure.
"""

from __future__ import annotations

from typing import Any, Protocol


class RagRepository(Protocol):
    """Port for searching and reading from the RAG vector store."""

    def get_collection_name(self) -> str:
        """Return the current collection name (e.g. from last crawl or default)."""
        ...

    def supports_hybrid(self) -> bool:
        """True if the backing collection has sparse vectors (dense+sparse hybrid search)."""
        ...

    def search(
        self,
        vector: list[float],
        top_k: int,
        filter_dict: dict[str, Any] | None = None,
        *,
        sparse_indices: list[int] | None = None,  # noqa: ARG002
        sparse_values: list[float] | None = None,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        """Search for similar points by dense vector; optionally fuse with sparse (hybrid).

        Args:
            vector: The dense query vector.
            top_k: The number of results to return.
            filter_dict: Optional metadata filters.
            sparse_indices: Optional indices for sparse vector (hybrid search).
            sparse_values: Optional values for sparse vector (hybrid search).

        Returns:
            A list of hits, each containing "id", "score", and "payload".

        Note:
            When sparse_indices/sparse_values are provided and supports_hybrid() is True,
            implementations should use hybrid fusion (e.g. RRF); otherwise dense-only.
        """
        ...


__all__ = ["RagRepository"]
