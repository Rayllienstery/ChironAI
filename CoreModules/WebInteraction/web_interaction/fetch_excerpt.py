"""Optional fetch of one allowed HTML page into plain text (env-gated)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

Snippet = dict[str, str]

USER_AGENT = "ChironAI-WebInteraction/1.0 (local RAG proxy; excerpt fetch)"
MAX_BYTES = 512 * 1024
TIMEOUT_S = 8.0
MAX_EXCERPT_CHARS = 4000

_ALLOWED_HOSTS = frozenset(
    {
        "developer.apple.com",
        "swift.org",
        "github.com",
        "raw.githubusercontent.com",
        "huggingface.co",
        "arxiv.org",
        "docs.python.org",
        "developer.mozilla.org",
        "en.wikipedia.org",
        "wikipedia.org",
    }
)
_SKIP_HOSTS = frozenset({"youtube.com", "youtu.be", "m.youtube.com"})


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


def github_to_raw(url: str) -> str:
    """Map a GitHub blob/repo URL to raw.githubusercontent.com when possible."""
    try:
        p = urlparse((url or "").strip())
    except Exception:
        return url
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com":
        return url
    parts = [x for x in (p.path or "").split("/") if x]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, ref = parts[0], parts[1], parts[3]
        rest = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rest}"
    if len(parts) >= 2 and parts[0] not in {"topics", "search", "orgs", "settings", "notifications"}:
        owner, repo = parts[0], parts[1]
        ref = "HEAD"
        if len(parts) >= 4 and parts[2] == "tree":
            ref = parts[3]
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/README.md"
    return url


def excerpt_url_allowed(url: str) -> bool:
    h = _host(url)
    if h in _SKIP_HOSTS:
        return False
    return _host(github_to_raw(url)) in _ALLOWED_HOSTS


def fetch_page_excerpt(url: str) -> tuple[str, str]:
    """
    If env enabled and URL host allowed, GET page and return (plain_text, url).
    On failure returns ("", "").
    """
    if not fetch_page_env_enabled() or not (url or "").strip():
        return "", ""
    url = github_to_raw(url)
    if not excerpt_url_allowed(url):
        return "", ""
    try:
        import requests
    except ImportError:
        return "", ""

    ctype = ""

    try:
        with requests.get(
            url,
            timeout=TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        ) as r:
            r.raise_for_status()
            ctype = (r.headers.get("Content-Type") or "").lower()
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

    if "html" not in ctype and not raw.lstrip()[:15].lower().startswith("<!doctype") and "<html" not in raw[:400].lower():
        text = raw
    else:
        try:
            import html2text

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
    for item in ranked[:3]:
        u = (item.get("url") or "").strip()
        if not u or _host(u) in _SKIP_HOSTS:
            continue
        text, url = fetch_page_excerpt(u)
        if text:
            return text, url
    return "", ""
