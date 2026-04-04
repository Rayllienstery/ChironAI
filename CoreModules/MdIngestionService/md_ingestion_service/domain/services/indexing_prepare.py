"""
Single pipeline: raw crawled markdown -> optional skip + body ready for chunking.

Order (must match docs / tests):
1. parse_and_strip_meta_block
2. filename excludes (indexing.yaml exclude_filename_substrings)
3. content head markers (exclude_content_head_chars + exclude_content_substrings)
4. md_indexer pipeline (includes reject_low_signal_body step in JSON — min_chars/word/alpha checks)
5. if pipeline unavailable: same reject step via modules.md_indexer.application.steps
6. strip noise sections (noise_section_headings)
7. collapse excessive blank lines (_strip_markdown_simple equivalent)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

try:
    from config import get_indexing_int, get_indexing_list
except ImportError:

    def get_indexing_int(key: str, default: int) -> int:
        return default

    def get_indexing_list(key: str, default: list) -> list:
        return default if isinstance(default, list) else []


try:
    from domain.services.markdown_meta import parse_and_strip_meta_block
except ImportError:
    parse_and_strip_meta_block = None  # type: ignore[assignment,misc]

try:
    from modules.md_indexer import get_active_pipeline_name, run_pipeline as run_md_indexer_pipeline
except ImportError:
    get_active_pipeline_name = None  # type: ignore[assignment,misc]
    run_md_indexer_pipeline = None  # type: ignore[assignment,misc]

try:
    from modules.md_indexer.application.steps import (
        DEFAULT_REJECT_LOW_SIGNAL_PARAMS,
        step_reject_low_signal_body,
    )
except ImportError:
    step_reject_low_signal_body = None  # type: ignore[assignment,misc]
    DEFAULT_REJECT_LOW_SIGNAL_PARAMS = {}  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class PrepareResult:
    """Outcome of prepare_markdown_for_indexing."""

    skipped: bool
    skip_reason: str | None  # machine code: too_short, filename_excluded, content_excluded, empty_after_prepare
    page_meta: dict[str, Any]
    body_md: str
    skip_detail: str | None = None


def _collapse_whitespace(md: str) -> str:
    if not md:
        return ""
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def strip_noise_section_headings(md: str, noise_headings: list[str]) -> str:
    """
    Drop markdown sections whose heading title (any level #) matches a noise label.
    Skip from the noise heading until the next heading at the same or higher level (fewer #'s).
    """
    if not md or not noise_headings:
        return md
    noise_norm = {h.strip().casefold() for h in noise_headings if h and str(h).strip()}
    if not noise_norm:
        return md
    lines = md.split("\n")
    out: list[str] = []
    skipping = False
    noise_level = 6

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            level = 0
            for c in stripped:
                if c == "#":
                    level += 1
                else:
                    break
            title = stripped[level:].strip()
            if title.casefold() in noise_norm:
                skipping = True
                noise_level = level
                continue
            if skipping and level > 0 and level <= noise_level:
                skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out)


def _filename_excluded(filename: str, patterns: list[str]) -> bool:
    if not filename or not patterns:
        return False
    lower = filename.lower()
    return any(p and p.lower() in lower for p in patterns)


def _content_head_excluded(body: str, head_chars: int, markers: list[str]) -> bool:
    if not body or not markers:
        return False
    head = body[: max(0, head_chars)]
    for m in markers:
        if m and m in head:
            return True
    return False


def prepare_markdown_for_indexing(
    filename: str,
    raw_md: str,
    *,
    run_pipeline_fn: Callable[[str, str], tuple[dict[str, Any], str]] | None = None,
    active_pipeline_name_fn: Callable[[], str] | None = None,
) -> PrepareResult:
    """
    Prepare markdown for RAG chunking. ``filename`` is the basename or path used for filename-based excludes.

    Optional injectors default to md_indexer when importable; tests can pass mocks.
    """
    empty_meta: dict[str, Any] = {}
    if parse_and_strip_meta_block is None:
        return PrepareResult(
            skipped=True,
            skip_reason="other",
            page_meta=empty_meta,
            body_md="",
            skip_detail="markdown_meta unavailable",
        )
    if not raw_md:
        return PrepareResult(
            skipped=True,
            skip_reason="too_short",
            page_meta=empty_meta,
            body_md="",
            skip_detail="empty file",
        )

    page_meta, body = parse_and_strip_meta_block(raw_md)

    fn_patterns = get_indexing_list("exclude_filename_substrings", [])
    if _filename_excluded(filename, fn_patterns):
        return PrepareResult(
            skipped=True,
            skip_reason="filename_excluded",
            page_meta=page_meta,
            body_md="",
            skip_detail=filename,
        )

    head_n = get_indexing_int("exclude_content_head_chars", 2000)
    content_markers = get_indexing_list("exclude_content_substrings", [])
    if _content_head_excluded(body, head_n, content_markers):
        return PrepareResult(
            skipped=True,
            skip_reason="content_excluded",
            page_meta=page_meta,
            body_md="",
            skip_detail="exclude_content_substrings match in head",
        )

    rp = run_pipeline_fn or run_md_indexer_pipeline
    ap = active_pipeline_name_fn or get_active_pipeline_name
    if rp is not None and ap is not None:
        try:
            _meta_extra, body = rp(ap(), body)
            if isinstance(_meta_extra, dict) and _meta_extra:
                page_meta = {**page_meta, **_meta_extra}
        except Exception:
            pass

    noise = get_indexing_list("noise_section_headings", [])
    body = strip_noise_section_headings(body, noise)
    body = _collapse_whitespace(body)

    # Final gate: same rule as pipeline step reject_low_signal_body (YAML noise can shrink text).
    if step_reject_low_signal_body is not None and DEFAULT_REJECT_LOW_SIGNAL_PARAMS:
        body = step_reject_low_signal_body(body, dict(DEFAULT_REJECT_LOW_SIGNAL_PARAMS))

    if not body.strip():
        return PrepareResult(
            skipped=True,
            skip_reason="empty_after_prepare",
            page_meta=page_meta,
            body_md="",
            skip_detail="no body after pipeline",
        )

    return PrepareResult(
        skipped=False,
        skip_reason=None,
        page_meta=page_meta,
        body_md=body,
    )


__all__ = [
    "PrepareResult",
    "prepare_markdown_for_indexing",
    "strip_noise_section_headings",
]
