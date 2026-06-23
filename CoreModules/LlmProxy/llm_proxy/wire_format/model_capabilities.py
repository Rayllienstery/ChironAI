"""Provider capability helpers used by OpenAI-compatible chat mapping."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests


def _ollama_tags_url_from_chat_url(chat_url: str) -> str | None:
    raw = (chat_url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = parsed.path or ""
    if path.endswith("/api/chat"):
        base_path = path[: -len("/api/chat")]
    elif "/api/" in path:
        base_path = path.split("/api/", 1)[0]
    else:
        base_path = path.rstrip("/")
    tags_path = f"{base_path.rstrip('/')}/api/tags"
    return urlunparse((parsed.scheme, parsed.netloc, tags_path, "", "", ""))


def _model_name_from_tag(row: dict[str, Any]) -> str:
    return str(row.get("name") or row.get("model") or "").strip()


@lru_cache(maxsize=64)
def _cached_ollama_tags(tags_url: str, minute_bucket: int) -> dict[str, frozenset[str]]:
    _ = minute_bucket
    try:
        resp = requests.get(tags_url, timeout=2.5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, TypeError):
        return {}
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return {}
    out: dict[str, frozenset[str]] = {}
    for item in models:
        if not isinstance(item, dict):
            continue
        name = _model_name_from_tag(item)
        if not name:
            continue
        raw_caps = item.get("capabilities")
        if not isinstance(raw_caps, list):
            continue
        out[name] = frozenset(str(cap).strip().lower() for cap in raw_caps if str(cap).strip())
    return out


def get_cached_ollama_capabilities(model: str, chat_url: str) -> frozenset[str] | None:
    tags_url = _ollama_tags_url_from_chat_url(chat_url)
    key = (model or "").strip()
    if not tags_url or not key:
        return None
    tags = _cached_ollama_tags(tags_url, int(time.time() // 60))
    return tags.get(key)


def caps_supports_tools(caps: frozenset[str]) -> bool:
    return "tools" in caps


def caps_supports_vision(caps: frozenset[str]) -> bool:
    return "vision" in caps or "image" in caps or "images" in caps


def caps_supports_thinking(caps: frozenset[str]) -> bool:
    return "thinking" in caps or "think" in caps


def find_cached_ollama_vision_model(
    chat_url: str,
    *,
    preferred_models: tuple[str, ...] = (),
) -> str | None:
    tags_url = _ollama_tags_url_from_chat_url(chat_url)
    if not tags_url:
        return None
    tags = _cached_ollama_tags(tags_url, int(time.time() // 60))
    if not tags:
        return None
    for model in preferred_models:
        name = (model or "").strip()
        if name and caps_supports_vision(tags.get(name, frozenset())):
            return name
    for name, caps in tags.items():
        if caps_supports_vision(caps):
            return name
    return None


def ollama_native_think_troublesome_model(model_name: str | None) -> bool:
    return "qwen3" in (model_name or "").lower()


def chat_error_suggests_no_tools(exc: BaseException) -> bool:
    return "does not support tools" in str(exc).lower()


def chat_error_suggests_no_think(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "does not support think" in s or "unsupported think" in s or "think is not supported" in s
