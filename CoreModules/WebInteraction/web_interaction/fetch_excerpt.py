"""Optional fetch of one allowed HTML page into plain text (env-gated)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

Snippet = dict[str, str]

USER_AGENT = "ChironAI-WebInteraction/1.0 (local RAG proxy; excerpt fetch)"
MAX_BYTES = 512 * 1024
TIMEOUT_S = 8.0
MAX_EXCERPT_CHARS = 4000

_ALLOWED_HOSTS = frozenset({"developer.apple.com", "swift.org"})


def fetch_page_env_enabled() -> bool:
    raw = os.environ.get("WEB_INTERACTION_FETCH_PAGE")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _host(url: str) -> str:
    try:
        p = urlparse((url or "").strip())
        h = (p.netloc or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def excerpt_url_allowed(url: str) -> bool:
    return _host(url) in _ALLOWED_HOSTS


def fetch_page_excerpt(url: str) -> tuple[str, str]:
    """
    If env enabled and URL host allowed, GET page and return (plain_text, url).
    On failure returns ("", "").
    """
    if not fetch_page_env_enabled() or not (url or "").strip():
        return "", ""
    if not excerpt_url_allowed(url):
        return "", ""
    try:
        import html2text
        import requests
    except ImportError:
        return "", ""

    try:
        with requests.get(
            url,
            timeout=TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        ) as r:
            r.raise_for_status()
            chunks = bytearray()
            for chunk in r.iter_content(65536):
                if not chunk:
                    continue
                chunks.extend(chunk)
                if len(chunks) >= MAX_BYTES:
                    break
        raw = bytes(chunks).decode("utf-8", errors="replace")
    except Exception:
        return "", ""

    try:
        h2t = html2text.HTML2Text()
        h2t.ignore_links = True
        h2t.ignore_images = True
        text = h2t.handle(raw)
    except Exception:
        return "", ""

    text = " ".join(text.split())
    if len(text) > MAX_EXCERPT_CHARS:
        cut = text[: MAX_EXCERPT_CHARS + 1]
        dot = cut.rfind(". ")
        text = (cut[:dot] + ".").strip() if dot > MAX_EXCERPT_CHARS // 2 else cut.strip()

    return text, url


def excerpt_for_top_snippet(ranked: list[Snippet]) -> tuple[str, str]:
    if not ranked:
        return "", ""
    u = (ranked[0].get("url") or "").strip()
    return fetch_page_excerpt(u)
