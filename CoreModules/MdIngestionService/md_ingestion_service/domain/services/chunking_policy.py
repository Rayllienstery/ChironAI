"""
Chunking policy: split normalized text into chunks with section path.

Delegates to same logic as rag_service chunking (split by headings, min/max size).
Can be configured via project root config when run from repo.
"""

from __future__ import annotations

from typing import Any

CHUNK_MAX_SIZE = 1200
CHUNK_MIN_SIZE = 300


def chunk_quality_ok(text: str) -> bool:
    if not (text or "").strip():
        return False
    words = (text or "").split()
    return len(words) >= 25


def split_markdown_into_chunks(
    md: str,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
) -> list[tuple[str, list[str]]]:
    if not md:
        return []
    max_sz = max_chunk_size or CHUNK_MAX_SIZE
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    chunks: list[tuple[str, list[str]]] = []
    current: list[str] = []
    current_len = 0
    section_path: list[str] = []
    for p in paragraphs:
        stripped = p.lstrip()
        if stripped.startswith("#"):
            depth = 0
            while depth < len(stripped) and stripped[depth] == "#":
                depth += 1
            title = stripped[depth:].strip()
            if depth >= 1 and title:
                section_path = section_path[: depth - 1] + [title]
        if current_len + len(p) + 2 > max_sz and current:
            text = "\n\n".join(current)
            chunks.append((text, list(section_path)))
            current = [p]
            current_len = len(p) + 2
        else:
            current.append(p)
            current_len += len(p) + 2
    if current:
        chunks.append(("\n\n".join(current), list(section_path)))
    return chunks


def chunks_for_document(
    text: str,
    source_id: str,
    filename: str,
    path: str = "",
    url: str | None = None,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
) -> list[dict[str, Any]]:
    """Split text into chunks and return list of payload dicts (text, source_id, path, url, section_path)."""
    raw_chunks = split_markdown_into_chunks(text, max_chunk_size, min_chunk_size)
    out = []
    for chunk_text, section_path in raw_chunks:
        if not chunk_quality_ok(chunk_text):
            continue
        out.append({
            "text": chunk_text,
            "source_id": source_id,
            "path": path or filename,
            "url": url or "",
            "section_path": section_path,
        })
    return out


__all__ = ["chunks_for_document", "chunk_quality_ok", "split_markdown_into_chunks"]
