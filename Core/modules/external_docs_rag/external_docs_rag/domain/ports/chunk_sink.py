"""Port for writing chunks (with vectors) to a RAG store."""

from __future__ import annotations

from typing import Any, Protocol


class ChunkSink(Protocol):
    """Port for writing chunk payloads and vectors to a named collection."""

    def write_chunks(
        self,
        collection_name: str,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
        vector_size: int,
    ) -> int:
        """
        Write chunks and their vectors to the collection.
        Create collection if it does not exist (with vector_size).
        Returns number of points written.
        """
        ...


__all__ = ["ChunkSink"]
