"""
Domain-level markdown chunking.

Pure business logic for:
- Splitting markdown into chunks with section_path (heading hierarchy).
- Merging adjacent small chunks in the same section.
- Quality check: minimum word count and alpha ratio (filters nav/footer noise).

Configurable via config.get_indexing_* with sensible defaults.
"""

from __future__ import annotations

from typing import List, Tuple

try:
    from config import get_indexing_float, get_indexing_int  # type: ignore
except ImportError:
    get_indexing_int = lambda k, d: d  # noqa: E731
    get_indexing_float = lambda k, d: d  # noqa: E731


CHUNK_MAX_SIZE: int = get_indexing_int("chunk_max_size", 1200)
CHUNK_MIN_SIZE: int = get_indexing_int("chunk_min_size", 300)
MIN_CHUNK_WORDS: int = get_indexing_int("min_chunk_words", 25)
MIN_CHUNK_ALPHA_RATIO: float = get_indexing_float("min_chunk_alpha_ratio", 0.2)


def chunk_quality_ok(text: str) -> bool:
    """
    Return False if the chunk is too short or mostly non-alphabetic (nav/footer noise).
    """
    if not text or not (text or "").strip():
        return False
    words = (text or "").split()
    if len(words) < MIN_CHUNK_WORDS:
        return False
    alpha = sum(1 for c in text if c.isalpha())
    total = sum(1 for c in text if not c.isspace())
    if total == 0:
        return False
    if alpha / total < MIN_CHUNK_ALPHA_RATIO:
        return False
    return True


def split_markdown_into_chunks(
    md: str,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
) -> List[Tuple[str, List[str]]]:
    """
    Split markdown into chunks with section_path (heading hierarchy).
    Returns list of (chunk_text, section_path). section_path is e.g. ["Concurrency", "Actors"].
    Prefers starting new chunks at headings; enforces min/max chunk size.
    Merges adjacent chunks below min_chunk_size when same section_path.
    """
    max_sz = max_chunk_size if max_chunk_size is not None else CHUNK_MAX_SIZE
    min_sz = min_chunk_size if min_chunk_size is not None else CHUNK_MIN_SIZE
    if not md:
        return []
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    chunks: List[Tuple[str, List[str]]] = []
    current: List[str] = []
    current_len = 0
    section_path: List[str] = []

    def _flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        text = "\n\n".join(current)
        chunks.append((text, list(section_path)))
        current.clear()
        current_len = 0

    for p in paragraphs:
        stripped = p.lstrip()
        is_heading = stripped.startswith("#")
        if is_heading:
            depth = 0
            while depth < len(stripped) and stripped[depth] == "#":
                depth += 1
            title = stripped[depth:].strip()
            if depth >= 1 and title:
                section_path = section_path[: depth - 1] + [title]
            if current and current_len >= max_sz * 0.5:
                _flush()
            current.append(p)
            current_len += len(p) + 2
            continue
        if current_len + len(p) + 2 > max_sz and current:
            _flush()
            current = [p]
            current_len = len(p) + 2
        else:
            current.append(p)
            current_len += len(p) + 2
    _flush()

    merged: List[Tuple[str, List[str]]] = []
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


__all__ = [
    "chunk_quality_ok",
    "split_markdown_into_chunks",
    "CHUNK_MAX_SIZE",
    "CHUNK_MIN_SIZE",
    "MIN_CHUNK_WORDS",
    "MIN_CHUNK_ALPHA_RATIO",
]
