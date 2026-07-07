"""DuckDuckGo text search (no API key)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

Snippet = dict[str, str]


def _snippet_from_ddg_dict(r: dict[str, str]) -> Snippet | None:
    if not isinstance(r, dict):
        return None
    title = str(r.get("title") or "").strip()
    href = str(r.get("href") or r.get("url") or "").strip()
    body = str(r.get("body") or "").strip()
    if not href and not body:
        return None
    return {"title": title, "url": href, "body": body}


def _normalize_url_key(url: str) -> str:
    u = (url or "").strip().lower()
    if not u:
        return ""
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (p.path or "").rstrip("/")
        return f"{host}{path}"
    except Exception:
        return u


def search_snippets(
    query: str,
    max_n: int,
    *,
    region: str | None = None,
) -> list[Snippet]:
    """
    Return up to max_n results: {title, url, body} (body = snippet text).
    Empty list on failure or empty query.

    duckduckgo_search's public ``text()`` currently forces the Bing backend only; in many
    regions or when Bing HTML changes, it returns no rows. We fall back to DDG lite, then
    DDG html (same as the library's private backends) when the primary path is empty.
    """
    q = (query or "").strip()
    if not q or max_n <= 0:
        return []
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    out: list[Snippet] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(q, region=region, max_results=max_n):
                sn = _snippet_from_ddg_dict(r) if isinstance(r, dict) else None
                if sn:
                    out.append(sn)
                if len(out) >= max_n:
                    break
    except Exception:  # safe: DDG primary search best-effort; fallbacks below
        pass

    def _merge_fallback(rows: list[dict[str, str]] | None) -> None:
        seen = {_normalize_url_key(s.get("url") or "") for s in out if s.get("url")}
        for r in rows or []:
            if len(out) >= max_n:
                break
            sn = _snippet_from_ddg_dict(r)
            if not sn:
                continue
            key = _normalize_url_key(sn.get("url") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(sn)

    if len(out) < max_n:
        try:
            with DDGS() as ddgs:
                lite_rows = ddgs._text_lite(q, region=region, timelimit=None, max_results=max_n)
            _merge_fallback(lite_rows)
        except Exception:  # safe: DDG lite fallback best-effort
            pass

    if len(out) < max_n:
        try:
            with DDGS() as ddgs:
                html_rows = ddgs._text_html(q, region=region, timelimit=None, max_results=max_n)
            _merge_fallback(html_rows)
        except Exception:  # safe: DDG html fallback best-effort
            pass

    return out[:max_n]


def search_snippets_multi(
    queries: list[str],
    max_n: int,
    *,
    region: str | None = None,
    per_query_cap: int | None = None,
) -> list[Snippet]:
    """
    Run multiple queries, merge results, dedupe by normalized URL, keep order of first appearance.
    """
    if not queries or max_n <= 0:
        return []
    cap = per_query_cap if per_query_cap is not None else max(max_n, 5)
    seen: set[str] = set()
    merged: list[Snippet] = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        batch = search_snippets(q, cap, region=region)
        for s in batch:
            key = _normalize_url_key(s.get("url") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(s)
            if len(merged) >= max_n * 2:
                break
        if len(merged) >= max_n * 2:
            break
    return merged


def search_snippets_with_backend(
    query: str,
    max_n: int,
    backend: Any,
    *,
    region: str | None = None,
) -> list[Snippet]:
    """
    Test hook: backend is a callable (query, max_n) -> list[Snippet].
    """
    if backend is None:
        return search_snippets(query, max_n, region=region)
    if callable(backend):
        raw = backend(query, max_n)
        return list(raw) if raw else []
    return search_snippets(query, max_n, region=region)


def search_news_snippets(
    query: str,
    max_n: int,
    *,
    region: str | None = None,
) -> list[Snippet]:
    """DDG news (past month); unstable API; optional via WEB_INTERACTION_DDG_NEWS."""
    q = (query or "").strip()
    if not q or max_n <= 0:
        return []
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    reg = region if region else "wt-wt"
    out: list[Snippet] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.news(q, region=reg, timelimit="m", max_results=max_n):
                if not isinstance(r, dict):
                    continue
                title = str(r.get("title") or "").strip()
                href = str(r.get("link") or r.get("url") or "").strip()
                body = str(r.get("body") or r.get("excerpt") or r.get("source") or "").strip()
                if not href and not body:
                    continue
                out.append({"title": title or "News", "url": href, "body": body})
                if len(out) >= max_n:
                    break
    except Exception:
        return []
    return out


def search_multi_with_backend(
    queries: list[str],
    max_n: int,
    backend: Any,
    *,
    region: str | None = None,
) -> list[Snippet]:
    """Multi-query with optional per-query callable backend (tests)."""
    if backend is None:
        return search_snippets_multi(queries, max_n, region=region)
    if callable(backend):
        merged: list[Snippet] = []
        seen: set[str] = set()
        for q in queries:
            raw = backend(q, max_n)
            for s in raw or []:
                key = _normalize_url_key((s or {}).get("url") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(s)
        return merged
    return search_snippets_multi(queries, max_n, region=region)
