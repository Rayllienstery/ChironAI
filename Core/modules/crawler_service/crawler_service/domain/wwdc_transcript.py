"""WWDC transcript TSV/JSON parsing and markdown rendering."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def parse_wwdc_event_year(event: str) -> int | None:
    """Parse WWDC event label like 'WWDC24' or 'WWDC2024' into a four-digit year."""
    if not event:
        return None
    event = event.strip().upper()
    if not event.startswith("WWDC"):
        return None
    suffix = event[4:]
    if not suffix.isdigit():
        return None
    if len(suffix) == 2:
        year = 2000 + int(suffix)
    else:
        year = int(suffix)
    return year


def extract_wwdc_session_id_from_url(url: str) -> tuple[int | None, str | None]:
    """Extract (year, session_id) from Apple transcript URL when possible."""
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
    except Exception:
        return None, None
    m = re.search(r"wwdc(\d{4})-(\d+)-transcript", path)
    if not m:
        return None, None
    year = int(m.group(1))
    session_id = m.group(2)
    return year, session_id


def flatten_wwdc_transcript_json(data: object) -> list[dict[str, str | None]]:
    """Flatten WWDC transcript JSON into ordered speech segments."""
    segments: list[dict[str, str | None]] = []

    def visit(node: object) -> None:
        if isinstance(node, list):
            if (
                len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], str)
            ):
                cleaned = " ".join(node[1].split())
                if cleaned:
                    segments.append({"speaker": None, "text": cleaned})
                return
            for item in node:
                visit(item)
            return

        if isinstance(node, dict):
            text = None
            speaker = None
            for key, value in node.items():
                kl = str(key).lower()
                if isinstance(value, str):
                    if kl in ("text", "body", "caption", "utterance"):
                        if text is None:
                            text = value
                    elif kl in ("speaker", "name", "presenter"):
                        speaker = value
            if text:
                cleaned = " ".join(text.split())
                if cleaned:
                    segments.append({"speaker": speaker, "text": cleaned})
            for v in node.values():
                visit(v)

    visit(data)
    deduped: list[dict[str, str | None]] = []
    last_text: str | None = None
    for seg in segments:
        text = seg.get("text") or ""
        if not text or text == last_text:
            continue
        last_text = text
        deduped.append(seg)
    return deduped


def wwdc_segments_to_markdown(
    *,
    url: str,
    event: str,
    year: int | None,
    session_id: str | None,
    title: str,
    segments: list[dict[str, str | None]],
) -> str:
    """Render WWDC transcript segments to RAG-optimized markdown (no md_indexer here)."""
    lines: list[str] = []

    _FLUFF_SENTENCES: set[str] = {
        "thanks for joining me",
        "thank you for joining me",
        "thank you for watching",
        "thanks for watching",
        "thank you for watching and goodbye",
        "thank you, and see you around",
        "thank you and see you around",
        "see you around",
        "see you next time",
        "thank you",
        "that's so cool",
        "ooh, shiny",
        "yeah. it was a big day",
        "it was a big day",
        "seventeen big and little things from apple wwdc23",
        "get all the updates on apple.com",
    }

    _FLUFF_PREFIXES: tuple[str, ...] = (
        "for more information",
        "for more details",
        "to learn more",
        "to learn how",
        "to learn more about",
        "check out ",
        "be sure to watch",
        "get all the updates on",
        "our entire team is incredibly thrilled",
        "we hope that",
        "we hope you'll",
        "i hope they will",
    )

    _sentence_split_re = re.compile(r"(?<=[.!?])\s+")

    def _strip_wwdc_fluff_from_text(text: str) -> str:
        if not text:
            return ""
        parts = _sentence_split_re.split(text)
        kept: list[str] = []
        for raw in parts:
            s = " ".join(raw.strip().split())
            if not s:
                continue
            norm = s.lower()
            norm_stripped = norm.rstrip(".!?:\"'“”")
            if norm_stripped in _FLUFF_SENTENCES:
                continue
            if any(norm_stripped.startswith(p) for p in _FLUFF_PREFIXES):
                continue
            if "♪" in s:
                continue
            kept.append(s)
        return " ".join(kept)

    lines.append("<!--")
    lines.append("meta:")
    lines.append(f"  url: {url}")
    lines.append(f"  event: {event}")
    if year is not None:
        lines.append(f"  year: {year}")
    if session_id is not None:
        lines.append(f"  session_id: {session_id}")
    lines.append("  doc_kind: wwdc_session")
    lines.append("-->")
    lines.append("")

    lines.append(f"# {title}")
    lines.append("")

    if year is not None or session_id is not None:
        meta_parts: list[str] = []
        if year is not None:
            meta_parts.append(str(year))
        meta_parts.append(event)
        if session_id is not None:
            meta_parts.append(f"Session {session_id}")
        lines.append(" · ".join(meta_parts))
        lines.append("")

    current_speaker: str | None = None
    current_text_parts: list[str] = []

    def flush_paragraph() -> None:
        nonlocal current_speaker, current_text_parts
        if not current_text_parts:
            return
        para = " ".join(" ".join(current_text_parts).split())
        if not para:
            current_text_parts = []
            return
        if current_speaker:
            lines.append(f"**{current_speaker}:** {para}")
        else:
            lines.append(para)
        lines.append("")
        current_text_parts = []

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        text = _strip_wwdc_fluff_from_text(text)
        if not text:
            continue
        speaker = seg.get("speaker")
        if len(text) <= 3 and text.lower() in {"um", "uh", "so"}:
            continue
        if speaker != current_speaker and current_text_parts:
            flush_paragraph()
        current_speaker = speaker
        current_text_parts.append(text)

    flush_paragraph()

    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md


__all__ = [
    "parse_wwdc_event_year",
    "extract_wwdc_session_id_from_url",
    "flatten_wwdc_transcript_json",
    "wwdc_segments_to_markdown",
]
