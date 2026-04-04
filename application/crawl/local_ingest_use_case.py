"""
Local markdown ingest use case.

Ingest a folder of markdown files into the vector store via embedding provider
and index writer (Qdrant). Uses domain chunking and metadata inference.
"""

from __future__ import annotations

from typing import Any


def ingest_markdown_folder(
    markdown_dir: str,
    source_id: str,
    embed_provider: Any,  # EmbeddingProvider - kept as Any for now as this is a stub
    _index_writer: Any,  # Index writer interface - reserved for future wiring
    _chunking_service: Any,  # Chunking service - reserved for future wiring
    metadata_inference: Any,  # Metadata inference - kept as Any for now as this is a stub
) -> dict[str, Any]:
    """
    Read markdown files from markdown_dir, chunk, embed, and upsert to index.
    Returns summary: { "files_processed": int, "chunks_indexed": int, "errors": list }.
    """
    # Stub: full implementation can delegate to WebUI/ingest_markdown_local.py
    # or use MarkdownStore.list_filenames + read_markdown, then chunk, embed, upsert.
    return {"files_processed": 0, "chunks_indexed": 0, "errors": []}


__all__ = ["ingest_markdown_folder"]
