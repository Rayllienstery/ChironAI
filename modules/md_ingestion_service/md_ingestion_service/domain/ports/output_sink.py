"""
Output sink port: write chunked documents to RAG (e.g. via HTTP to rag_service).
"""

from __future__ import annotations

from typing import Any, Protocol


class OutputSink(Protocol):
    """Port for sending chunked payloads to the RAG index (e.g. rag_service)."""

    def write_chunks(
        self,
        collection: str,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]] | None = None,
    ) -> int:
        """
        Write chunks to the RAG store. If vectors is None, the sink may call embed internally.
        Returns number of points written.
        """
        ...


__all__ = ["OutputSink"]
