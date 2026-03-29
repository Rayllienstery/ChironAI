"""Short TTL in-process cache for ranked web snippets."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Any

from web_interaction.search import Snippet

_lock = threading.Lock()
_store: dict[str, tuple[float, list[Snippet], dict[str, Any]]] = {}


def cache_ttl_seconds() -> float:
    raw = os.environ.get("WEB_INTERACTION_CACHE_TTL_S")
    if raw is None or str(raw).strip() == "":
        return 180.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 180.0


def make_cache_key(
    queries: list[str],
    trigger: str,
    max_n: int,
    region: str,
    *,
    variant: str = "",
) -> str:
    payload = "|".join([trigger, str(max_n), region or "", variant, *queries])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_get(key: str) -> tuple[list[Snippet], dict[str, Any]] | None:
    ttl = cache_ttl_seconds()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        ts, snippets, aux = entry
        if now - ts > ttl:
            del _store[key]
            return None
        return [dict(s) for s in snippets], dict(aux)


def cache_set(key: str, snippets: list[Snippet], aux: dict[str, Any] | None = None) -> None:
    ttl = cache_ttl_seconds()
    if ttl <= 0:
        return
    now = time.monotonic()
    frozen = [dict(s) for s in snippets]
    extra = dict(aux or {})
    with _lock:
        _store[key] = (now, frozen, extra)
        if len(_store) > 256:
            _prune_unlocked(now, ttl)


def _prune_unlocked(now: float, ttl: float) -> None:
    dead = [k for k, (ts, _, _) in _store.items() if now - ts > ttl]
    for k in dead:
        del _store[k]
    if len(_store) > 256:
        for k in list(_store.keys())[:50]:
            del _store[k]


def cache_clear_for_tests() -> None:
    with _lock:
        _store.clear()
