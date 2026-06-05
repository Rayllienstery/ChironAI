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
8. fallback reject_low_signal_body only when md_indexer pipeline is unavailable/fails
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
    prepare_stats: dict[str, int] | None = None


def _collapse_whitespace(md: str) -> str:
    if not md:
        return ""
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _has_substantial_prose(text: str) -> bool:
    for para in text.split("\n\n"):
        p = para.strip()
        if len(p) < 120:
            continue
        alpha = sum(1 for c in p if c.isalpha())
        if alpha / max(len(p), 1) < 0.5:
            continue
        if p.startswith("[") or p.startswith("http"):
            continue
        return True
    return False


def strip_leading_toc(md: str) -> str:
    """Drop leading nav/breadcrumb junk before the first H1 when it is not real prose."""
    if not md or not md.strip():
        return md
    lines = md.split("\n")
    h1_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^#\s+\S", line.strip()):
            h1_idx = i
            break
    if h1_idx is None or h1_idx == 0:
        return md
    prefix = "\n".join(lines[:h1_idx])
    if _has_substantial_prose(prefix):
        return md
    return "\n".join(lines[h1_idx:])


_STORE_CTA_SUBSTRINGS = (
    "sponsor the site",
    "twitter.com/twostraws",
    "buy our books",
    "click here to visit the hacking with swift store",
    "become a member",
    "sign up for our newsletter",
    "subscribe to our newsletter",
    "state of subscription apps",
    "utm_source=hackingwithswift",
    "utm_source=hacking",
    "revenuecat.com",
    "winwinkit.com",
    "everything-but-the-code",
    "swift-ai-playbook",
)

_COMMUNITY_FOOTER_TAIL_MARKERS: dict[str, tuple[str, ...]] = {
    "hackingwithswift": (
        "#### [__ mastodon",
        "#### [__ email",
        "[about](/about) [glossary](/glossary)",
        "swift, swiftui, the swift logo",
        "hacking with swift is",
        "you are not logged in",
        "link copied to your pasteboard",
        "was this page useful?",
        "average rating:",
    ),
    "objc_io": (
        "### year 1",
        "### year 2",
        "#### objc.io",
    ),
    "pointfree": (
        "#### [point-free](/)",
        "##### content",
        "##### hosts",
        "##### about",
    ),
}

_COMMUNITY_PARAGRAPH_DROP_SUBSTRINGS = (
    "sponsored",
    "utm_source=hackingwithswift",
    "utm_source=hacking",
    "revenuecat.com",
    "winwinkit.com",
    "was this page useful?",
    "average rating:",
    "you are not logged in",
    "link copied to your pasteboard",
)


def _normalize_heading_label(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    text = re.sub(r"[_*`~]+", " ", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _drop_paragraphs_containing(md: str, substrings: tuple[str, ...]) -> str:
    if not md or not substrings:
        return md
    paragraphs = re.split(r"(\n\s*\n)", md)
    out: list[str] = []
    for part in paragraphs:
        if not part.strip() or part.strip() == "":
            out.append(part)
            continue
        lower = part.lower()
        if any(sub in lower for sub in substrings):
            continue
        out.append(part)
    return "".join(out)


def _truncate_at_community_footer(md: str, site: str) -> str:
    markers = _COMMUNITY_FOOTER_TAIL_MARKERS.get(site, ())
    if not md or not markers:
        return md
    lines = md.split("\n")
    for i, line in enumerate(lines):
        lower = line.lower().strip()
        if any(marker in lower for marker in markers):
            prefix = "\n".join(lines[:i]).strip()
            if prefix:
                return prefix
            return ""
    return md


def _is_community_hub_page(url: str, site: str) -> bool:
    u = (url or "").strip().lower().rstrip("/")
    if not u:
        return False
    if site == "hackingwithswift":
        if u in {
            "https://www.hackingwithswift.com/example-code",
            "https://www.hackingwithswift.com/quick-start/swiftui",
            "https://www.hackingwithswift.com/read",
        }:
            return True
        return re.match(r"^https://www\.hackingwithswift\.com/example-code/[^/]+$", u) is not None
    if site == "objc_io":
        return u == "https://www.objc.io/issues"
    if site == "pointfree":
        return u == "https://www.pointfree.co/collections"
    return False


def strip_community_boilerplate(md: str, source_extra: dict[str, Any] | None) -> str:
    """Remove repeated community nav/footer/ad blocks before chunking."""
    if not md:
        return md
    site = str((source_extra or {}).get("site") or "").strip().lower()
    if not site:
        return md
    cleaned = _drop_paragraphs_containing(md, _COMMUNITY_PARAGRAPH_DROP_SUBSTRINGS)
    cleaned = _truncate_at_community_footer(cleaned, site)
    return cleaned


def strip_store_cta_lines(md: str) -> str:
    """Remove community store/sponsor CTA lines."""
    if not md:
        return md
    out: list[str] = []
    for line in md.split("\n"):
        lower = line.lower()
        if any(sub in lower for sub in _STORE_CTA_SUBSTRINGS):
            continue
        out.append(line)
    return "\n".join(out)


def apply_source_prepare_options(body: str, source_extra: dict[str, Any] | None) -> str:
    """Apply per-source flags from config/sources.yaml extra (strip_toc, strip_store_cta)."""
    extra = source_extra or {}
    md = body
    if extra.get("strip_toc"):
        md = strip_leading_toc(md)
    if extra.get("strip_store_cta"):
        md = strip_store_cta_lines(md)
    md = strip_community_boilerplate(md, extra)
    return md


def strip_noise_section_headings(md: str, noise_headings: list[str]) -> str:
    """
    Drop markdown sections whose heading title (any level #) matches a noise label.
    Skip from the noise heading until the next heading at the same or higher level (fewer #'s).
    """
    if not md or not noise_headings:
        return md
    noise_norm = {_normalize_heading_label(str(h)) for h in noise_headings if h and str(h).strip()}
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
            title_norm = _normalize_heading_label(title)
            if title_norm in noise_norm:
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
    source_extra: dict[str, Any] | None = None,
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
            prepare_stats={
                "raw_chars": len(raw_md or ""),
                "body_original_chars": 0,
                "body_prepared_chars": 0,
                "removed_chars": 0,
            },
        )
    if not raw_md:
        return PrepareResult(
            skipped=True,
            skip_reason="too_short",
            page_meta=empty_meta,
            body_md="",
            skip_detail="empty file",
            prepare_stats={
                "raw_chars": 0,
                "body_original_chars": 0,
                "body_prepared_chars": 0,
                "removed_chars": 0,
            },
        )

    page_meta, body = parse_and_strip_meta_block(raw_md)

    source_extra = source_extra or {}

    # Guard against Apple Developer portal navigation pages being crawled under doc URLs.
    # These pages are low-signal and pollute retrieval (e.g. /documentation/swiftui/observable returning site navigation).
    try:
        url = str((page_meta or {}).get("url") or "").strip().rstrip("/")
        if url.endswith("/documentation/swiftui/observable"):
            portal_markers = ("Stay Updated", "Explore Platforms", "Explore Technologies", "Explore Community")
            hits = sum(1 for m in portal_markers if m in body)
            if hits >= 2:
                return PrepareResult(
                    skipped=True,
                    skip_reason="content_excluded",
                    page_meta=page_meta,
                    body_md="",
                    skip_detail="apple_portal_navigation_page",
                )
    except Exception:
        pass

    site = str(source_extra.get("site") or "").strip().lower()
    if _is_community_hub_page(str((page_meta or {}).get("url") or ""), site):
        return PrepareResult(
            skipped=True,
            skip_reason="content_excluded",
            page_meta=page_meta,
            body_md="",
            skip_detail="community_hub_page",
        )
    original_body_chars = len(body or "")

    def _prepare_stats(prepared_body: str) -> dict[str, int]:
        prepared_chars = len(prepared_body or "")
        return {
            "raw_chars": len(raw_md or ""),
            "body_original_chars": original_body_chars,
            "body_prepared_chars": prepared_chars,
            "removed_chars": max(0, original_body_chars - prepared_chars),
        }

    fn_patterns = get_indexing_list("exclude_filename_substrings", [])
    if _filename_excluded(filename, fn_patterns):
        return PrepareResult(
            skipped=True,
            skip_reason="filename_excluded",
            page_meta=page_meta,
            body_md="",
            skip_detail=filename,
            prepare_stats=_prepare_stats(body),
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
            prepare_stats=_prepare_stats(body),
        )

    rp = run_pipeline_fn or run_md_indexer_pipeline
    ap = active_pipeline_name_fn or get_active_pipeline_name
    pipeline_applied = False
    if rp is not None and ap is not None:
        try:
            _meta_extra, body = rp(ap(), body)
            if isinstance(_meta_extra, dict) and _meta_extra:
                page_meta = {**page_meta, **_meta_extra}
            pipeline_applied = True
        except Exception:
            pass

    noise = get_indexing_list("noise_section_headings", [])
    body = strip_noise_section_headings(body, noise)
    body = apply_source_prepare_options(body, source_extra)
    body = _collapse_whitespace(body)

    # Final gate fallback when md_indexer pipeline isn't available (or failed before applying).
    # If pipeline ran, its own reject_low_signal_body step is the single source of truth.
    if (not pipeline_applied) and step_reject_low_signal_body is not None and DEFAULT_REJECT_LOW_SIGNAL_PARAMS:
        body = step_reject_low_signal_body(body, dict(DEFAULT_REJECT_LOW_SIGNAL_PARAMS))

    if not body.strip():
        return PrepareResult(
            skipped=True,
            skip_reason="empty_after_prepare",
            page_meta=page_meta,
            body_md="",
            skip_detail="no body after pipeline",
            prepare_stats=_prepare_stats(body),
        )

    return PrepareResult(
        skipped=False,
        skip_reason=None,
        page_meta=page_meta,
        body_md=body,
        prepare_stats=_prepare_stats(body),
    )


__all__ = [
    "PrepareResult",
    "apply_source_prepare_options",
    "prepare_markdown_for_indexing",
    "strip_leading_toc",
    "strip_community_boilerplate",
    "strip_noise_section_headings",
    "strip_store_cta_lines",
]
