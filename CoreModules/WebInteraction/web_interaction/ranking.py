"""Rank and filter DuckDuckGo snippets by domain heuristics."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from web_interaction.search import Snippet

# Higher score = better (we sort descending)
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


_BLOCKLIST_SUBSTR = (
    "pinterest.",
    "quora.com",
    "medium.com/m",
    "linkedin.com/pulse",
    "facebook.com",
)


def _host(url: str) -> str:
    try:
        p = urlparse((url or "").strip())
        h = (p.netloc or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _domain_score(url: str) -> int:
    h = _host(url)
    u = (url or "").lower()
    score = 0
    for dom in _preferred_domains():
        if dom in h or h.endswith(dom):
            score += 10
    if "documentation" in u and "apple.com" in h:
        score += 5
    if "github.com" in h:
        score += 6
    return score


def _is_blocked(url: str) -> bool:
    h = _host(url)
    u = (url or "").lower()
    return any(bad in h or bad in u for bad in _BLOCKLIST_SUBSTR)


def rank_and_trim(snippets: list[Snippet], max_n: int) -> list[Snippet]:
    """
    Drop blocklisted URLs, sort by domain preference and snippet length, keep max_n.
    """
    if not snippets or max_n <= 0:
        return []
    filtered: list[Snippet] = []
    for s in snippets:
        url = (s.get("url") or "").strip()
        if url and _is_blocked(url):
            continue
        filtered.append(s)

    def sort_key(s: Snippet) -> tuple[int, int]:
        url = s.get("url") or ""
        body = s.get("body") or ""
        return (_domain_score(url), len(body))

    filtered.sort(key=sort_key, reverse=True)
    return filtered[:max_n]


def top_domains(snippets: list[Snippet], k: int = 3) -> list[str]:
    seen: list[str] = []
    for s in snippets:
        h = _host(s.get("url") or "")
        if h and h not in seen:
            seen.append(h)
        if len(seen) >= k:
            break
    return seen
