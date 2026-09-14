"""Query rewrite and result ranking for local SearxNG / DDG web search.

Keep in sync with ``plugins/web/searxng/quality.py`` in the Hermes agent.
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlparse

_FENCE_RE = re.compile(r"```[\w]*\n[\s\S]*?```|```[\s\S]*?```", re.MULTILINE)
_TOKEN_RE = re.compile(r"[^\w.+-]+", re.UNICODE)
_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_BANG_RE = re.compile(r"^!\S+\s+")
_MAX_PLUS_RE = re.compile(r"\bMax\+", re.IGNORECASE)
_PERSONA_VOCATIVE_RE = re.compile(
    r"^(?:ковальски[йи]?|kowalski|шкипер|skipper)\b[\s,!.:;\-—–/]*",
    re.IGNORECASE,
)

IT_KEYS = (
    "github",
    "huggingface",
    "hf.co",
    "gguf",
    "llama.cpp",
    "llama cpp",
    "vllm",
    "comfyui",
    "qdrant",
    "gitlab",
    "stackoverflow",
    "npm ",
    "pypi",
    "crates.io",
    "docker hub",
    "ggml",
)
SCI_KEYS = (
    "arxiv",
    "paper",
    "survey",
    "paged attention",
    "flashattention",
    "flash attention",
)
NEWS_KEYS = (
    "новости",
    "новост",
    "breaking news",
    "news today",
    "главные новости",
)

BOOST_HOSTS = (
    "github.com",
    "huggingface.co",
    "arxiv.org",
    "developer.apple.com",
    "swift.org",
    "stackoverflow.com",
    "docs.python.org",
    "docs.searxng.org",
    "z.ai",
    "unsloth.ai",
    "ollama.com",
    "lmstudio.ai",
    "pytorch.org",
    "nvidia.com",
    "amd.com",
    "kernel.org",
    "ietf.org",
    "wikipedia.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "theguardian.com",
    "rbc.ru",
    "ria.ru",
    "lenta.ru",
    "interfax.ru",
    "tass.ru",
    "meduza.io",
    "hermes-agent.nousresearch.com",
)

REMOVE_HOSTS = (
    "temu.com",
    "thehiddenwiki.com",
    "jingyan.baidu.com",
    "justgetflux.com",
    "pinterest.com",
    "pinterest.",
    "zaun-idee.de",
    "locations.papajohns.com",
    "taboola.com",
    "outbrain.com",
    "zhihu.com",
    "zhihu.cn",
    "zhuanlan.zhihu.com",
)

LOW_HOSTS = (
    "amazon.com",
    "amazon.",
    "aliexpress.com",
    "ebay.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "hermes.com",
    "outlook.office.com",
    "to-do.office.com",
    "medium.com",
    "fandom.com",
    "wikihow.com",
    "quora.com",
    "linkedin.com",
    "maps.google.",
    "expedia.com",
    "mcmaster.com",
    "chatgpt.com",
    "play.google.com",
    "apps.apple.com",
    "shuminoengei.jp",
    "clubic.com",
)

_HOME_PARTS = frozenset(
    {"en", "en-us", "en.html", "index.html", "index.htm", "home", "us", "ru", "uk", "de", "fr"}
)


def compact_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub(" ", text or "")


def host_of(url: str) -> str:
    try:
        h = urlparse((url or "").strip()).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _path_parts(url: str) -> list[str]:
    try:
        return [p for p in urlparse((url or "").strip()).path.split("/") if p]
    except Exception:
        return []


def is_homepage(url: str) -> bool:
    parts = _path_parts(url)
    if not parts:
        return True
    if len(parts) == 1 and parts[0].lower() in _HOME_PARTS:
        return True
    return False


def _host_match(host: str, needles: tuple[str, ...]) -> bool:
    h = (host or "").lower()
    for n in needles:
        n = n.lower()
        if n.endswith("."):
            if n in h or h.endswith(n.rstrip(".")):
                return True
            continue
        if h == n or h.endswith("." + n):
            return True
    return False


_ADULT_TLDS = frozenset({"xxx", "sex", "porn", "adult"})
_ADULT_HOST_NEEDLES = (
    "pornhub.",
    "xvideos.",
    "xnxx.",
    "xhamster.",
    "nudevista.",
    "spicymature.",
    "japxtube.",
    "sos.xxx",
    "onlyfans.",
    "redtube.",
    "youporn.",
    "chaturbate.",
)


def is_adult_url(url: str) -> bool:
    host = host_of(url)
    if not host:
        return False
    tld = host.rsplit(".", 1)[-1]
    if tld in _ADULT_TLDS:
        return True
    return _host_match(host, _ADULT_HOST_NEEDLES)


def is_removed_url(url: str) -> bool:
    if is_adult_url(url):
        return True
    return _host_match(host_of(url), REMOVE_HOSTS)


def is_low_url(url: str) -> bool:
    h = host_of(url)
    if _host_match(h, LOW_HOSTS):
        return True
    if h == "stackoverflow.com":
        parts = _path_parts(url)
        if not parts or parts[0] not in {"questions", "q", "a"}:
            return True
    if h == "youtube.com" or h == "youtu.be":
        return True
    return False


def boost_points(url: str, extra_hosts: tuple[str, ...] = ()) -> int:
    h = host_of(url)
    u = (url or "").lower()
    score = 0
    if _host_match(h, BOOST_HOSTS):
        score += 12
    for dom in extra_hosts:
        d = (dom or "").strip().lower()
        if d and (d in h or h.endswith(d)):
            score += 10
    if "documentation" in u and "apple.com" in h:
        score += 6
    if h == "github.com" and len(_path_parts(url)) >= 2:
        score += 4
    if h == "huggingface.co" and len(_path_parts(url)) >= 2:
        score += 4
    if h == "arxiv.org":
        score += 6
    if h == "stackoverflow.com" and any(p in _path_parts(url)[:1] for p in ("questions", "q")):
        score += 4
    return score


def query_tokens(query: str) -> list[str]:
    return [w for w in _TOKEN_RE.split((query or "").lower()) if len(w) >= 3]


def token_overlap(query: str, title: str, url: str, body: str) -> float:
    words = query_tokens(query)
    if not words:
        return 0.0
    blob = f"{title} {url} {body}".lower()
    return sum(1 for w in words if w in blob) / len(words)


def looks_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def infer_language(query: str) -> str | None:
    if looks_cyrillic(query):
        return "ru-RU"
    if re.search(r"[A-Za-z]", query or ""):
        return "en-US"
    return None


def infer_categories(query: str) -> str:
    q = compact_ws(query or "")
    if not q or q.startswith("!"):
        return ""
    low = q.lower()
    cats = ["general"]
    if any(k in low for k in IT_KEYS):
        cats.append("it")
    if any(k in low for k in SCI_KEYS):
        cats.append("science")
    if any(k in low for k in NEWS_KEYS):
        cats.append("news")
    return ",".join(cats)


def strip_persona_vocatives(text: str) -> str:
    """Drop leading Kowalski/Skipper address tokens; keep leftover query."""
    q = compact_ws(text or "")
    while q:
        m = _PERSONA_VOCATIVE_RE.match(q)
        if not m:
            break
        nxt = compact_ws(q[m.end() :])
        if not nxt:
            break
        q = nxt
    return q


def rewrite_query(query: str) -> str:
    raw = compact_ws(strip_code_fences(query or ""))
    if not raw:
        return ""
    bang = ""
    m = _BANG_RE.match(raw)
    if m:
        bang = m.group(0)
        raw = raw[m.end() :]
    q = strip_persona_vocatives(_MAX_PLUS_RE.sub("Max Plus", raw))
    if not q:
        return compact_ws(bang)
    low = q.lower()
    extras: list[str] = []
    if re.search(r"flux[\s.]*2|\bflux2\b|klein\s*9", low) and "justgetflux" not in low:
        extras.append("-justgetflux")
    if re.search(r"\bhermes\s+agent\b", low) and "hermes.com" not in low:
        extras.append("-site:hermes.com")
        if "nous" not in low:
            extras.append("nousresearch")
    if re.search(r"strix\s+halo", low) and "amd" not in low and "ryzen" not in low:
        extras.append("AMD")
        extras.append("-pentest")
    if extras:
        q = f"{q} {' '.join(extras)}"
    return compact_ws(bang + q)


def _engine_names(item: Mapping[str, Any]) -> list[str]:
    raw = item.get("engines") or item.get("engine")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw if x]
    return []


def quality_score(
    item: Mapping[str, Any],
    query: str,
    extra_boost_hosts: tuple[str, ...] = (),
) -> float:
    url = str(item.get("url") or "")
    title = str(item.get("title") or "")
    body = str(item.get("body") or item.get("content") or item.get("description") or "")
    try:
        base = float(item.get("score") or 0.0)
    except (TypeError, ValueError):
        base = 0.0
    score = base
    score += boost_points(url, extra_boost_hosts)
    score += token_overlap(query, title, url, body) * 10.0
    low_q = (query or "").lower()
    if "developer.apple.com" in host_of(url) and any(
        k in low_q for k in ("apple", "swiftui", "uikit", "uiviewcontroller", "wwdc", "swift ")
    ):
        score += 10.0
    if host_of(url) == "developer.mozilla.org" and not any(
        k in low_q for k in ("mdn", "javascript", "css", "http", "dom", "web api")
    ):
        score -= 12.0
    if is_homepage(url):
        score -= 16.0
    if is_low_url(url):
        score -= 18.0
    engines = [e.lower() for e in _engine_names(item)]
    if (
        engines
        and all(e == "yandex" for e in engines)
        and not looks_cyrillic(query)
        and boost_points(url, extra_boost_hosts) <= 0
    ):
        score -= 6.0
    return score


def rank_results(
    items: list[Mapping[str, Any]],
    max_n: int,
    query: str = "",
    extra_boost_hosts: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    if not items or max_n <= 0:
        return []
    filtered: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if url and is_removed_url(url):
            continue
        key = url.rstrip("/").lower() if url else str(item.get("title") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        filtered.append(item)
    filtered.sort(
        key=lambda it: quality_score(it, query, extra_boost_hosts),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for item in filtered[:max_n]:
        out.append(dict(item))
    return out
