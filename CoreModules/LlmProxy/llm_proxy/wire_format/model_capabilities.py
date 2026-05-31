"""Discover provider-native model capabilities via POST /api/show, with a short TTL cache."""

from __future__ import annotations

import logging
import time

import requests

_LOG = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str], tuple[float, frozenset[str] | None]] = {}
_TTL_SEC = 300.0


def ollama_base_url_from_chat_url(chat_url: str) -> str:
    u = chat_url.rstrip("/")
    low = u.lower()
    if low.endswith("/api/chat"):
        return u[: -len("/api/chat")]
    return u.rsplit("/", 1)[0]


def fetch_ollama_capabilities(*, model: str, chat_url: str, timeout: float = 8.0) -> frozenset[str] | None:
    name = (model or "").strip()
    if not name:
        return None
    base = ollama_base_url_from_chat_url(chat_url)
    url = f"{base.rstrip('/')}/api/show"
    try:
        r = requests.post(url, json={"model": name}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _LOG.debug("provider /api/show failed model=%s: %s", name, e)
        return None
    if not isinstance(data, dict):
        return None
    caps = data.get("capabilities")
    if caps is None:
        return None
    if not isinstance(caps, list):
        return None
    out = frozenset(str(x).strip().lower() for x in caps if isinstance(x, str) and str(x).strip())
    return out


def get_cached_ollama_capabilities(model: str, chat_url: str) -> frozenset[str] | None:
    key = ((model or "").strip(), (chat_url or "").strip())
    if not key[0] or not key[1]:
        return None
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit is not None:
        ts, val = hit
        if now - ts < _TTL_SEC:
            return val
    val = fetch_ollama_capabilities(model=key[0], chat_url=key[1])
    _CACHE[key] = (now, val)
    return val


def caps_supports_tools(caps: frozenset[str]) -> bool:
    return "tools" in caps


def caps_supports_thinking(caps: frozenset[str]) -> bool:
    return "thinking" in caps or "think" in caps


def ollama_native_think_troublesome_model(model_name: str | None) -> bool:
    return "qwen3" in (model_name or "").lower()


def chat_error_suggests_no_tools(exc: BaseException) -> bool:
    return "does not support tools" in str(exc).lower()


def chat_error_suggests_no_think(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "does not support think" in s or "unsupported think" in s or "think is not supported" in s
