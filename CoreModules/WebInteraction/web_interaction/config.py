"""Env-based toggles for web interaction (no paid API keys)."""

from __future__ import annotations

import os


def env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def max_results_default() -> int:
    raw = os.environ.get("WEB_INTERACTION_MAX_RESULTS")
    if raw is None or str(raw).strip() == "":
        return 3
    try:
        n = int(raw)
        return max(1, min(5, n))
    except ValueError:
        return 3


def web_interaction_globally_enabled() -> bool:
    """Master kill-switch via WEB_INTERACTION_ENABLED (default on)."""
    return env_flag("WEB_INTERACTION_ENABLED", True)


def ddg_news_enabled() -> bool:
    """Optional DDG news results merged into snippet pool (freshness)."""
    raw = os.environ.get("WEB_INTERACTION_DDG_NEWS")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def ddg_region_for_message(user_message: str) -> str | None:
    """
    DuckDuckGo region: explicit WEB_INTERACTION_DDG_REGION, else ru-ru if Cyrillic in message.
    None = library default.
    """
    raw = os.environ.get("WEB_INTERACTION_DDG_REGION")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip()
    for c in user_message or "":
        if "\u0400" <= c <= "\u04ff":
            return "ru-ru"
    return None
