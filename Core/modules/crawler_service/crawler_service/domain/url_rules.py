"""URL allow/deny rules for deep crawl."""

from __future__ import annotations

from urllib.parse import urlparse


def crawl_url_allowed(
    url: str,
    depth: int,
    max_depth: int,
    start_parsed,
    base_url: str,
    prefix_p: str,
    doc_only: bool,
    visited: set[str],
    *,
    path_roots: list[str],
    excluded_substrings: list[str],
) -> bool:
    """Return True if (url, depth) should be crawled. path_roots = framework allowlist (per-source or default)."""
    if url in visited or depth > max_depth:
        return False
    parsed = urlparse(url)
    if parsed.netloc != start_parsed.netloc:
        return False
    path_p = (parsed.path or "").rstrip("/")
    if not (path_p == prefix_p or path_p.startswith(prefix_p + "/")):
        return False
    if doc_only and "/documentation" not in (parsed.path or ""):
        return False
    if any(sub in path_p.lower() for sub in excluded_substrings):
        return False
    for root in path_roots:
        r = (root or "").rstrip("/")
        if not r:
            continue
        if path_p == r or path_p.startswith(r + "/"):
            return True
    return False


def link_passes_filters(
    next_url: str,
    start_parsed,
    prefix_p: str,
    doc_only: bool,
    *,
    path_roots: list[str],
    excluded_substrings: list[str],
) -> bool:
    """Check discovered link for BFS enqueue."""
    try:
        next_parsed = urlparse(next_url)
        if next_parsed.netloc != start_parsed.netloc:
            return False
        next_path = (next_parsed.path or "").rstrip("/")
        if not (next_path == prefix_p or next_path.startswith(prefix_p + "/")):
            return False
        if doc_only and "/documentation" not in (next_parsed.path or ""):
            return False
        if any(sub in next_path.lower() for sub in excluded_substrings):
            return False
        if not any(
            next_path == (root or "").rstrip("/") or next_path.startswith((root or "").rstrip("/") + "/")
            for root in path_roots
            if (root or "").rstrip("/")
        ):
            return False
        return True
    except Exception:
        return False
