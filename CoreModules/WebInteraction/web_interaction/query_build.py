"""Build DuckDuckGo query strings from chat text and trigger type."""

from __future__ import annotations

import re

from web_interaction.triggers import WebSupplementTrigger

_FENCE_RE = re.compile(r"```[\w]*\n[\s\S]*?```|```[\s\S]*?```", re.MULTILINE)
_VERSION_HINT_RE = re.compile(
    r"\bios\s*\d{1,2}\b|\b20\d{2}\b|swift\s*6|swift\s*5|xcode\s*\d",
    re.IGNORECASE,
)


def strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub(" ", text or "")


def compact_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def truncate_query(text: str, max_len: int = 280) -> str:
    t = compact_ws(text)
    if len(t) <= max_len:
        return t
    cut = t[: max_len + 1]
    sp = cut.rfind(" ")
    if sp > max_len // 2:
        return cut[:sp].strip()
    return t[:max_len].strip()


def build_search_queries(user_message: str, trigger: WebSupplementTrigger, *, max_len: int = 280) -> list[str]:
    """
    Return 1–2 search strings: primary cleaned message; optional second query by trigger.
    """
    cleaned = truncate_query(strip_code_fences(user_message or ""), max_len=max_len)
    if not cleaned:
        return []

    queries: list[str] = [cleaned]

    if trigger == "low_confidence_framework":
        site_q = f"{cleaned} site:developer.apple.com"
        if site_q != cleaned:
            queries.append(truncate_query(site_q, max_len=max_len + 40))

    if trigger == "keywords" and _VERSION_HINT_RE.search(cleaned):
        low = cleaned.lower()
        if "release" not in low and "релиз" not in low:
            alt = truncate_query(f"{cleaned} release", max_len=max_len + 20)
            if alt != cleaned and alt not in queries:
                queries.append(alt)

    # Cap at 2 DDG calls per plan
    out: list[str] = []
    for q in queries:
        q = compact_ws(q)
        if q and q not in out:
            out.append(q)
        if len(out) >= 2:
            break
    return out
