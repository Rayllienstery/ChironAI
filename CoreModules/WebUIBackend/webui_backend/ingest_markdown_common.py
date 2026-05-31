"""
Shared semantic chunking and Qdrant payload helpers for local markdown ingest scripts.

Uses rag_service.domain.services.chunking (heading/paragraph boundaries, code blocks) and
config indexing limits, aligned with api/http/webui_routes _create_collection_from_sources.

Payload: text, source, path, section_path, section_path_joined (for Qdrant filters).
"""

from __future__ import annotations

from typing import Any

try:
    from config import get_indexing_int
except ImportError:

    def get_indexing_int(key: str, default: int) -> int:
        return default

from rag_service.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks


def get_chunk_sizes() -> tuple[int, int]:
    max_sz = get_indexing_int("chunk_max_size", 1200)
    min_sz = get_indexing_int("chunk_min_size", 300)
    return max_sz, min_sz


def chunks_for_local_ingest(md: str) -> list[tuple[str, list[str]]]:
    """Split markdown into (text, section_path) chunks; drop low-quality pieces."""
    max_sz, min_sz = get_chunk_sizes()
    raw = split_markdown_into_chunks(md, max_chunk_size=max_sz, min_chunk_size=min_sz)
    return [(t, sp) for t, sp in raw if chunk_quality_ok(t)]


def qdrant_payload_local(rel_path: str, text: str, section_path: list[str]) -> dict[str, Any]:
    """
    Qdrant point payload for CLI ingest. `source` and `path` both use the file path relative
    to the ingest root (backward compatible with older rag clients that only read `source`).
    """
    joined = ":".join(section_path) if section_path else ""
    return {
        "text": text,
        "source": rel_path,
        "path": rel_path,
        "section_path": section_path,
        "section_path_joined": joined,
    }


def payloads_for_markdown(md: str, rel_path: str) -> list[dict[str, Any]]:
    """Build payload dicts for every accepted chunk (for tests and tooling)."""
    return [qdrant_payload_local(rel_path, t, sp) for t, sp in chunks_for_local_ingest(md)]


def print_local_ingest_summary(
    *,
    collection: str,
    total_chunks: int,
    files_total: int,
    files_indexed_ok: int,
    files_skipped_read_error: int,
    files_skipped_no_chunks: int,
    files_skipped_embed_error: int,
    files_skipped_embed_mismatch: int,
) -> None:
    """Stdout rollup for CLI markdown ingest scripts."""
    print("---")
    print("Ingest summary:")
    print(f"  files_total: {files_total}")
    print(f"  files_indexed_ok: {files_indexed_ok}")
    print(f"  files_skipped_read_error: {files_skipped_read_error}")
    print(f"  files_skipped_no_chunks: {files_skipped_no_chunks}")
    print(f"  files_skipped_embed_error: {files_skipped_embed_error}")
    print(f"  files_skipped_embed_mismatch: {files_skipped_embed_mismatch}")
    print(f"  total_chunks_upserted: {total_chunks}")
    print(f"  collection: {collection}")


__all__ = [
    "chunks_for_local_ingest",
    "get_chunk_sizes",
    "payloads_for_markdown",
    "print_local_ingest_summary",
    "qdrant_payload_local",
]
