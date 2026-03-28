"""Cross-request caches for tool/edit retry heuristics (Zed agent loops)."""

from __future__ import annotations

import time

recent_success: dict[tuple[str, str], float] = {}
recent_noop: dict[tuple[str, str], tuple[int, float]] = {}

_recent_success_ttl_s = 45.0
_recent_noop_ttl_s = 120.0


def configure_ttl(recent_success_ttl_s: float, recent_noop_ttl_s: float) -> None:
    global _recent_success_ttl_s, _recent_noop_ttl_s
    _recent_success_ttl_s = recent_success_ttl_s
    _recent_noop_ttl_s = recent_noop_ttl_s


def now_s() -> float:
    return time.time()


def prune_recent_success(now_s: float) -> None:
    if not recent_success:
        return
    cutoff = now_s - _recent_success_ttl_s
    stale = [k for k, ts in recent_success.items() if ts < cutoff]
    for k in stale:
        recent_success.pop(k, None)


def prune_recent_noop(now_s: float) -> None:
    if not recent_noop:
        return
    cutoff = now_s - _recent_noop_ttl_s
    stale = [k for k, (_, ts) in recent_noop.items() if ts < cutoff]
    for k in stale:
        recent_noop.pop(k, None)
