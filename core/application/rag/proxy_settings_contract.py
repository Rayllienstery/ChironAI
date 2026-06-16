"""
Explicit precedence contract for proxy/RAG settings.

This module centralizes setting resolution so behavior does not silently
change between environments or call paths.
"""

from __future__ import annotations

import json
from typing import Any, Callable

try:
    from config import get_retrieval_bool
except ImportError:
    get_retrieval_bool = lambda _k, d=False: d  # type: ignore[assignment]


def load_proxy_settings(settings_repo: Any) -> dict[str, Any]:
    """Load persisted `proxy_settings` JSON object; returns empty dict on any error."""
    try:
        raw = settings_repo.get_app_setting("proxy_settings")
        if not raw or not str(raw).strip():
            return {}
        loaded = json.loads(raw) if isinstance(raw, str) else raw
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def resolve_rag_collection(
    *,
    request_collection: str | None,
    settings_repo: Any,
    proxy_settings: dict[str, Any],
    app_key: str = "rag_collection",
) -> tuple[str | None, str]:
    """
    Resolve collection with explicit priority and source label.

    Priority:
    1) request `collection_name`
    2) app setting `rag_collection`
    3) legacy `proxy_settings.rag_collection`
    4) none (`default`)
    """
    req = str(request_collection or "").strip() or None
    if req:
        return req, "request"
    try:
        app_value = (settings_repo.get_app_setting(app_key) or "").strip() or None
    except Exception:
        app_value = None
    if app_value:
        return app_value, f"app_settings.{app_key}"
    legacy = (proxy_settings.get("rag_collection") or "").strip() if isinstance(proxy_settings, dict) else ""
    if legacy:
        return legacy, "proxy_settings.rag_collection"
    return None, "default"


def resolve_proxy_rerank_enabled(
    *,
    settings_repo: Any,
    proxy_settings: dict[str, Any],
    fallback_getter: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """
    Resolve rerank toggle for /v1 proxy path.

    Priority:
    1) `proxy_settings.rerank_for_rag` when key exists,
    2) static config/env fallback getter.
    """
    if isinstance(proxy_settings, dict) and "rerank_for_rag" in proxy_settings:
        return bool(proxy_settings.get("rerank_for_rag")), "proxy_settings.rerank_for_rag"
    # Reload once from repo in case caller provided a stale dict.
    live = load_proxy_settings(settings_repo)
    if "rerank_for_rag" in live:
        return bool(live.get("rerank_for_rag")), "proxy_settings.rerank_for_rag"
    if fallback_getter is None:
        return False, "default"
    try:
        return bool(fallback_getter()), "config.get_proxy_rerank_enabled"
    except Exception:
        return False, "default"


def resolve_hybrid_sparse_enabled(
    *,
    proxy_settings: dict[str, Any],
    yaml_default: bool | None = None,
) -> tuple[bool, str]:
    """Resolve hybrid sparse flag with explicit source label."""
    if isinstance(proxy_settings, dict) and "hybrid_sparse_enabled" in proxy_settings:
        return bool(proxy_settings.get("hybrid_sparse_enabled")), "proxy_settings.hybrid_sparse_enabled"
    default = get_retrieval_bool("hybrid_sparse_enabled", True) if yaml_default is None else bool(yaml_default)
    return bool(default), "retrieval_yaml.hybrid_sparse_enabled"


def resolve_fetch_web_knowledge(
    *,
    request_value: Any,
    proxy_settings: dict[str, Any],
    is_autocomplete: bool,
) -> tuple[bool, str]:
    """
    Resolve fetch_web_knowledge flag.

    Priority:
    1) request value when provided,
    2) persisted `proxy_settings.fetch_web_knowledge`,
    3) false default.
    Autocomplete always forces disabled with explicit source label.
    """
    if is_autocomplete:
        return False, "autocomplete_forced_off"
    if request_value is not None:
        return bool(request_value), "request.fetch_web_knowledge"
    if isinstance(proxy_settings, dict) and "fetch_web_knowledge" in proxy_settings:
        return bool(proxy_settings.get("fetch_web_knowledge")), "proxy_settings.fetch_web_knowledge"
    return False, "default"


def resolve_web_interaction_flags(
    *,
    proxy_settings: dict[str, Any],
    env_ddg_news: bool,
    env_fetch_page: bool,
    env_wikipedia: bool,
) -> dict[str, dict[str, Any]]:
    """
    Resolve web interaction flags with source for each key.

    For ddg/fetch/wiki keys, persisted proxy settings are authoritative when key
    exists; otherwise environment fallback is used.
    """
    out: dict[str, dict[str, Any]] = {}

    def _pick(key: str, default: bool, source_default: str) -> None:
        if isinstance(proxy_settings, dict) and key in proxy_settings:
            out[key] = {"value": bool(proxy_settings.get(key)), "source": f"proxy_settings.{key}"}
        else:
            out[key] = {"value": bool(default), "source": source_default}

    _pick("web_interaction_enabled", False, "default")
    _pick("web_interaction_on_keywords", True, "default")
    _pick("web_interaction_on_low_confidence_framework", True, "default")
    _pick("web_interaction_ddg_news", env_ddg_news, "env.ddg_news")
    _pick("web_interaction_fetch_page", env_fetch_page, "env.fetch_page")
    _pick("web_interaction_wikipedia", env_wikipedia, "env.wikipedia")
    return out


def resolve_retrieval_ui_bool(
    key: str,
    *,
    proxy_settings: dict[str, Any],
    yaml_fallback: bool = False,
) -> tuple[bool, str]:
    """Resolve retrieval UI bool keys with explicit source label."""
    base = get_retrieval_bool(key, yaml_fallback)
    if isinstance(proxy_settings, dict) and key in proxy_settings:
        return bool(proxy_settings.get(key)), f"proxy_settings.{key}"
    return bool(base), f"retrieval_yaml.{key}"


__all__ = [
    "load_proxy_settings",
    "resolve_fetch_web_knowledge",
    "resolve_hybrid_sparse_enabled",
    "resolve_proxy_rerank_enabled",
    "resolve_rag_collection",
    "resolve_retrieval_ui_bool",
    "resolve_web_interaction_flags",
]
