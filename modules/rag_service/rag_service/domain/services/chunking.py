"""
Domain-level markdown chunking.

Split markdown into chunks with section_path, merge small adjacent chunks, quality check.
Respects code blocks and tables; supports long-paragraph split and overlap.
Config from project root when run from repo.
"""

from __future__ import annotations

import re

try:
    from config import get_indexing_float, get_indexing_int
except ImportError:
    get_indexing_int = lambda k, d: d  # noqa: E731
    get_indexing_float = lambda k, d: d  # noqa: E731

CHUNK_MAX_SIZE: int = get_indexing_int("chunk_max_size", 1200)
CHUNK_MIN_SIZE: int = get_indexing_int("chunk_min_size", 300)
CHUNK_OVERLAP: int = get_indexing_int("chunk_overlap", 0)
MIN_CHUNK_WORDS: int = get_indexing_int("min_chunk_words", 25)
MIN_CHUNK_ALPHA_RATIO: float = get_indexing_float("min_chunk_alpha_ratio", 0.2)


def chunk_quality_ok(text: str) -> bool:
    """False if chunk is too short or mostly non-alphabetic."""
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


def _split_into_paragraphs(md: str) -> list[str]:
    """
    Split markdown into paragraphs respecting code blocks and tables.
    Fenced code blocks and markdown table lines are kept as single units.
    """
    if not md:
        return []
    lines = md.split("\n")
    paragraphs: list[str] = []
    current: list[str] = []
    in_fenced = False
    fence_char: str | None = None
    in_table = False

    def flush_paragraph() -> None:
        nonlocal current
        if current:
            text = "\n".join(current).strip()
            if text:
                paragraphs.append(text)
            current = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if in_fenced:
            current.append(line)
            if stripped.startswith("```") and (fence_char is None or stripped.startswith(fence_char)):
                in_fenced = False
                fence_char = None
                flush_paragraph()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            in_fenced = True
            fence_char = stripped[:3]
            current.append(line)
            i += 1
            continue

        if in_table:
            if stripped.startswith("|"):
                current.append(line)
                i += 1
                continue
            in_table = False
            flush_paragraph()
            continue

        if stripped.startswith("|") and "|" in stripped:
            flush_paragraph()
            in_table = True
            current.append(line)
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        current.append(line)
        i += 1

    flush_paragraph()
    return paragraphs


def _split_long_paragraph(text: str, max_sz: int) -> list[str]:
    """Split a single paragraph longer than max_sz by sentence or line boundaries."""
    if len(text) <= max_sz:
        return [text]
    parts: list[str] = []
    pattern = re.compile(r"(?<=[.!?])\s+(?=\S)|(?<=\n)(?=\S)")
    start = 0
    while start < len(text):
        remaining = text[start:]
        if len(remaining) <= max_sz:
            parts.append(remaining.strip())
            break
        chunk = remaining[: max_sz + 1]
        last_break = -1
        for m in pattern.finditer(chunk):
            if m.start() <= max_sz:
                last_break = m.start()
        if last_break <= 0:
            last_nl = chunk.rfind("\n")
            last_sp = chunk.rfind(" ")
            last_break = max(last_nl, last_sp)
        if last_break <= 0:
            last_break = max_sz
        part = remaining[: last_break].strip()
        if part:
            parts.append(part)
        start += last_break
        while start < len(text) and text[start] in " \t\n":
            start += 1
    return parts


def split_markdown_into_chunks(
    md: str,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[tuple[str, list[str]]]:
    """
    Split markdown into chunks with section_path (heading hierarchy).
    Returns list of (chunk_text, section_path). Respects code blocks and tables;
    splits long paragraphs by sentence; optional overlap.
    """
    max_sz = max_chunk_size if max_chunk_size is not None else CHUNK_MAX_SIZE
    min_sz = min_chunk_size if min_chunk_size is not None else CHUNK_MIN_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP
    if not md:
        return []
    paragraphs = _split_into_paragraphs(md)
    chunks: list[tuple[str, list[str]]] = []
    current: list[str] = []
    current_len = 0
    section_path: list[str] = []
    overlap_prefix: list[str] = [""]

    def _flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        text = "\n\n".join(current)
        chunks.append((text, list(section_path)))
        overlap_prefix[0] = ""
        if overlap and len(text) >= overlap:
            overlap_prefix[0] = text[-overlap:].strip()
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

        if overlap_prefix[0] and not current:
            p = overlap_prefix[0] + "\n\n" + p
            current_len += len(overlap_prefix[0]) + 2
            overlap_prefix[0] = ""

        if current_len + len(p) + 2 > max_sz and current:
            _flush()
            if overlap_prefix[0]:
                p = overlap_prefix[0] + "\n\n" + p
                current_len += len(overlap_prefix[0]) + 2
                overlap_prefix[0] = ""
            if len(p) > max_sz:
                for part in _split_long_paragraph(p, max_sz):
                    if current_len + len(part) + 2 > max_sz and current:
                        _flush()
                        if overlap_prefix[0]:
                            part = overlap_prefix[0] + "\n\n" + part
                            current_len += len(overlap_prefix[0]) + 2
                            overlap_prefix[0] = ""
                    current.append(part)
                    current_len += len(part) + 2
            else:
                current.append(p)
                current_len += len(p) + 2
        else:
            if len(p) > max_sz:
                for part in _split_long_paragraph(p, max_sz):
                    if current_len + len(part) + 2 > max_sz and current:
                        _flush()
                        if overlap_prefix[0]:
                            part = overlap_prefix[0] + "\n\n" + part
                            current_len += len(overlap_prefix[0]) + 2
                            overlap_prefix[0] = ""
                    current.append(part)
                    current_len += len(part) + 2
            else:
                current.append(p)
                current_len += len(p) + 2
    _flush()

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


__all__ = [
    "chunk_quality_ok",
    "split_markdown_into_chunks",
    "CHUNK_MAX_SIZE",
    "CHUNK_MIN_SIZE",
    "CHUNK_OVERLAP",
    "MIN_CHUNK_WORDS",
    "MIN_CHUNK_ALPHA_RATIO",
]
