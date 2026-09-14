"""Rank and filter web snippets by domain heuristics and query overlap."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from web_interaction.search import Snippet
from web_interaction.search_quality import rank_results

_DEFAULT_PREFERRED = (
    "developer.apple.com",
    "swift.org",
    "github.com",
    "apple.com",
)


def _preferred_domains() -> tuple[str, ...]:
    raw = os.environ.get("WEB_INTERACTION_PREFERRED_DOMAINS")
    if raw and str(raw).strip():
        parts = tuple(p.strip().lower() for p in str(raw).split(",") if p.strip())
        return parts if parts else _DEFAULT_PREFERRED
    return _DEFAULT_PREFERRED


def _host(url: str) -> str:
    try:
        p = urlparse((url or "").strip())
        h = (p.netloc or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def rank_and_trim(snippets: list[Snippet], max_n: int, query: str = "") -> list[Snippet]:
    """
    Drop junk hosts, boost docs/code sources, prefer query overlap, keep max_n.
    """
    ranked = rank_results(
        list(snippets or []),
        max_n,
        query=query,
        extra_boost_hosts=_preferred_domains(),
    )
    return ranked


def top_domains(snippets: list[Snippet], k: int = 3) -> list[str]:
    seen: list[str] = []
    for s in snippets:
        h = _host(s.get("url") or "")
        if h and h not in seen:
            seen.append(h)
        if len(seen) >= k:
            break
    return seen
