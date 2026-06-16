"""
Markdown chunking for external docs: split by headings, min/max size.
No external config dependency; same semantics as project indexing.
"""

from __future__ import annotations

CHUNK_MAX_SIZE = 1200
CHUNK_MIN_SIZE = 300
MIN_CHUNK_WORDS = 25


def chunk_quality_ok(text: str) -> bool:
    """False if chunk is too short."""
    if not (text or "").strip():
        return False
    return len((text or "").split()) >= MIN_CHUNK_WORDS


def split_markdown_into_chunks(
    md: str,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
) -> list[tuple[str, list[str]]]:
    """
    Split markdown into (text, section_path) by paragraphs and ## headings.
    """
    if not md:
        return []
    max_sz = max_chunk_size or CHUNK_MAX_SIZE
    min_sz = min_chunk_size or CHUNK_MIN_SIZE
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
    merged: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(chunks):
        text, path = chunks[i]
        while (
            i + 1 < len(chunks)
            and len(text) < min_sz
            and chunks[i + 1][1] == path
            and len(text) + 2 + len(chunks[i + 1][0]) <= max_sz
        ):
            i += 1
            text += "\n\n" + chunks[i][0]
        merged.append((text, path))
        i += 1
    return merged


__all__ = ["chunk_quality_ok", "split_markdown_into_chunks"]
