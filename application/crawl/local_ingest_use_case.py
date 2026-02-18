"""
Local markdown ingest use case.

Ingest a folder of markdown files into the vector store via embedding provider
and index writer (Qdrant). Uses domain chunking and metadata inference.
"""

from __future__ import annotations

from typing import Any, List


def ingest_markdown_folder(
    markdown_dir: str,
    source_id: str,
    embed_provider: Any,
    index_writer: Any,
    chunking_service: Any,
    metadata_inference: Any,
) -> dict[str, Any]:
    """
    Read markdown files from markdown_dir, chunk, embed, and upsert to index.
    Returns summary: { "files_processed": int, "chunks_indexed": int, "errors": list }.
    """
    # Stub: full implementation can delegate to WebUI/ingest_markdown_local.py
    # or use MarkdownStore.list_filenames + read_markdown, then chunk, embed, upsert.
    return {"files_processed": 0, "chunks_indexed": 0, "errors": []}


__all__ = ["ingest_markdown_folder"]
