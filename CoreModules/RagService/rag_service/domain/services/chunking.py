"""
Domain-level markdown chunking.

Pure business logic for:
- Splitting markdown into chunks with section_path (heading hierarchy).
- Merging adjacent small chunks in the same section.
- Quality check: minimum word count and alpha ratio (filters nav/footer noise).

Configurable via config.get_indexing_* with sensible defaults.
"""

from __future__ import annotations

import re

from rag_service.config import get_indexing_float, get_indexing_int


CHUNK_MAX_SIZE: int = get_indexing_int("chunk_max_size", 1200)
CHUNK_MIN_SIZE: int = get_indexing_int("chunk_min_size", 300)
CHUNK_OVERLAP: int = get_indexing_int("chunk_overlap", 0)
MIN_CHUNK_WORDS: int = get_indexing_int("min_chunk_words", 5)
MIN_CHUNK_ALPHA_RATIO: float = get_indexing_float("min_chunk_alpha_ratio", 0.2)

_COMMUNITY_SOURCE_IDS = frozenset(
    {
        "hws_swift",
        "objc_io_issues",
        "pointfree_collections",
        "swiftbysundell_articles",
    }
)
_HWS_FOOTER_MARKERS = (
    "#### [__ mastodon",
    "#### [__ email",
    "[about](/about) [glossary](/glossary)",
    "swift, swiftui, the swift logo",
    "hacking with swift is",
    "you are not logged in",
    "link copied to your pasteboard",
    "was this page useful?",
    "average rating:",
    "utm_source=hacking",
)
_COMMUNITY_LIST_MARKERS = (
    " articles in the swift knowledge base",
    "_articles_in_the_[swift_knowledge_base]",
)
_OBJC_ARCHIVE_MARKERS = (
    "### year 1",
    "### year 2",
    "* [#1 lighter view controllers]",
    "* [#13 architecture]",
)
_POINTFREE_FOOTER_MARKERS = (
    "#### [point-free](/)",
    "##### content",
    "a hub for advanced swift programming",
)
_WWDC_HEADER_ONLY = re.compile(
    r"^#\s+.+\n+(?:\d{4}\s*·\s*WWDC\d+\s*·\s*Session\s+\d+|#\s+\w+@WWDC\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _source_chunk_acceptable(text: str, source_id: str) -> bool:
    full = text or ""
    head = full[:240]
    lower = head.lower()
    full_lower = full.lower()
    if source_id in _COMMUNITY_SOURCE_IDS:
        if head.lstrip().startswith("[ ](/)"):
            return False
        if "[ forums ]" in lower or "sponsor the site" in lower:
            return False
        if "buy our books" in lower:
            return False
        if "sponsored" in full_lower and "utm_" in full_lower:
            return False
        if any(marker in full_lower for marker in _COMMUNITY_LIST_MARKERS):
            return False
    if source_id == "hws_swift":
        if any(marker in full_lower for marker in _HWS_FOOTER_MARKERS):
            return False
    if source_id == "objc_io_issues":
        if any(marker in full_lower for marker in _OBJC_ARCHIVE_MARKERS):
            return False
    if source_id == "pointfree_collections":
        if any(marker in full_lower for marker in _POINTFREE_FOOTER_MARKERS):
            return False
    if source_id.startswith("wwdc_sessions_"):
        stripped = (text or "").strip()
        if len(stripped) < 220 and _WWDC_HEADER_ONLY.match(stripped):
            return False
        if re.match(r"^#\s+\w+@WWDC\d+\s*$", stripped, re.IGNORECASE):
            return False
    if source_id == "apple_documentation" and _is_low_value_conforms_chunk(full):
        return False
    if "similar solutions" in lower and len((text or "").strip()) < 500:
        return False
    return True


def _is_low_value_conforms_chunk(text: str) -> bool:
    """Detect Apple API chunks that contain only a Conforms To protocol list."""
    stripped = (text or "").strip()
    if "### Conforms To" not in stripped:
        return False
    without_code = re.sub(r"```.*?```", "", stripped, flags=re.DOTALL)
    lines = [ln.strip() for ln in without_code.splitlines() if ln.strip()]
    if not any(ln == "### Conforms To" for ln in lines):
        return False
    bullet_lines = sum(1 for ln in lines if ln.startswith("-"))
    prose_lines = [
        ln
        for ln in lines
        if not ln.startswith("#") and not ln.startswith("-") and len(ln.split()) > 8
    ]
    prose_words = len(" ".join(prose_lines).split())
    return bullet_lines >= 3 and prose_words < 16


def chunk_quality_ok(text: str, *, source_id: str | None = None) -> bool:
    """
    Return False if the chunk is too short or mostly non-alphabetic (nav/footer noise).
    Optional source_id applies community/WWDC-specific rejection heuristics.
    """
    if not text or not (text or "").strip():
        return False
    if source_id and not _source_chunk_acceptable(text, source_id):
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
    Fenced code blocks (```...```) and markdown table lines (|...|) are kept
    as single units and not split on internal \\n\\n.
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
            # Fall through to process current line in normal mode.
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


def _is_heading_only_chunk(text: str) -> bool:
    """
    Return True if the chunk text consists only of markdown heading line(s) with no body.
    Such chunks are poor for embedding; we merge them with the next chunk when same section.
    """
    if not text or not text.strip():
        return False
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return False
    return all(ln.startswith("#") for ln in lines)


def _split_long_paragraph(text: str, max_sz: int) -> list[str]:
    """Split a single paragraph longer than max_sz by sentence or line boundaries."""
    if len(text) <= max_sz:
        return [text]
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return [text]
    parts: list[str] = []
    # Prefer splitting on sentence end (. ! ?) followed by space or newline.
    pattern = re.compile(r"(?<=[.!?])\s+(?=\S)|(?<=\n)(?=\S)")
    start = 0
    while start < len(text):
        remaining = text[start:]
        if len(remaining) <= max_sz:
            parts.append(remaining.strip())
            break
        chunk = remaining[: max_sz + 1]
        # Find last sentence or line boundary in chunk.
        last_break = -1
        for m in pattern.finditer(chunk):
            if m.start() <= max_sz:
                last_break = m.start()
        if last_break <= 0:
            # No sentence break; split on last newline or last space.
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


def _build_overlap_prefix(text: str, overlap: int) -> str:
    """Return a small context tail without starting mid-word or inside code."""
    if not overlap or len(text) < overlap:
        return ""
    stripped = text.strip()
    if not stripped or stripped.endswith("```"):
        return ""
    tail_window = stripped[-min(len(stripped), overlap * 3) :]
    if "```" in tail_window:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", tail_window)
    for sentence in reversed(sentences):
        candidate = sentence.strip()
        if 20 <= len(candidate) <= overlap:
            return candidate
    tail = stripped[-overlap:].strip()
    first_space = tail.find(" ")
    if first_space > 0 and first_space < len(tail) - 1:
        tail = tail[first_space + 1 :].strip()
    return tail


def split_markdown_into_chunks(
    md: str,
    max_chunk_size: int | None = None,
    min_chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[tuple[str, list[str]]]:
    """
    Split markdown into chunks with section_path (heading hierarchy).
    Returns list of (chunk_text, section_path). section_path is e.g. ["Concurrency", "Actors"].
    Prefers starting new chunks at headings; enforces min/max chunk size.
    Merges adjacent chunks below min_chunk_size when same section_path.
    Respects code blocks and tables (no split inside them); splits long paragraphs by sentence.
    Optional overlap: next chunk starts with tail of previous for context.
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
            overlap_prefix[0] = _build_overlap_prefix(text, overlap)
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

    # Merge heading-only chunks with the next chunk when same section_path, so each
    # chunk contains section header + content (better for embedding and answers).
    result: list[tuple[str, list[str]]] = []
    j = 0
    while j < len(merged):
        text_j, path_j = merged[j]
        if (
            j + 1 < len(merged)
            and _is_heading_only_chunk(text_j)
            and merged[j + 1][1] == path_j
        ):
            next_text, next_path = merged[j + 1]
            result.append((text_j + "\n\n" + next_text, next_path))
            j += 2
        else:
            result.append((text_j, path_j))
            j += 1
    return result


__all__ = [
    "chunk_quality_ok",
    "split_markdown_into_chunks",
    "CHUNK_MAX_SIZE",
    "CHUNK_MIN_SIZE",
    "CHUNK_OVERLAP",
    "MIN_CHUNK_WORDS",
    "MIN_CHUNK_ALPHA_RATIO",
]
