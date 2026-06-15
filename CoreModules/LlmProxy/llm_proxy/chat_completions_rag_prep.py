"""RAG collection and project-context prep helpers for chat completions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from llm_proxy.chat_completions_response_helpers import proxy_settings_optional_int


def build_framework_name_to_collection_map(rag_sources_config: list[Any]) -> dict[str, str]:
    """Map framework trigger keywords and external_source_id to Qdrant collection names."""
    name_to_collection: dict[str, str] = {}
    for cfg in rag_sources_config:
        trigger_keywords = getattr(cfg, "trigger_keywords", None) or []
        for kw in trigger_keywords:
            key = (kw or "").strip().lower()
            if key:
                name_to_collection[key] = cfg.collection_name
        external_id = (getattr(cfg, "external_source_id", None) or "").strip()
        if external_id:
            name_to_collection[external_id.lower()] = cfg.collection_name
    return name_to_collection


def resolve_framework_collection_ttl_days(
    settings_repo: Any | None,
    *,
    default_ttl_days: int,
) -> int:
    if settings_repo is None:
        return default_ttl_days
    try:
        ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
        if ttl_raw is not None and str(ttl_raw).strip() != "":
            return int(ttl_raw)
    except (TypeError, ValueError):
        pass
    except Exception:
        pass
    return default_ttl_days


def resolve_project_fresh_collections(
    frameworks: list[Any],
    *,
    name_to_collection: dict[str, str],
    settings_repo: Any | None,
    check_collection_freshness: Callable[[dict[str, str] | None, int], str],
    default_ttl_days: int,
) -> tuple[set[str] | None, list[tuple[str, str]]]:
    """
    Resolve fresh framework-linked collections and those needing background refresh.

    Returns:
        (fresh_collection_names, needs_refresh) where needs_refresh entries are
        (framework_id_lower, collection_name).
    """
    if not frameworks or not name_to_collection:
        return None, []

    ttl_days = resolve_framework_collection_ttl_days(
        settings_repo,
        default_ttl_days=default_ttl_days,
    )
    fresh_collections: list[str] = []
    needs_refresh: list[tuple[str, str]] = []
    for fw in frameworks:
        if not isinstance(fw, dict):
            continue
        name = (fw.get("name") or "").strip()
        if not name:
            continue
        coll = name_to_collection.get(name.lower())
        if not coll:
            continue
        meta = None
        if settings_repo is not None:
            try:
                meta = settings_repo.get_collection_meta(coll)
            except Exception:
                pass
        if check_collection_freshness(meta, ttl_days) == "fresh":
            if coll not in fresh_collections:
                fresh_collections.append(coll)
        else:
            needs_refresh.append((name.lower(), coll))
    fresh_names = set(fresh_collections) if fresh_collections else None
    return fresh_names, needs_refresh


def apply_proxy_context_char_limits(
    proxy_settings: dict[str, Any],
    *,
    effective_context_chunk_chars: int,
    effective_context_total_chars: int,
) -> tuple[int, int, int | None]:
    """Overlay proxy_settings context limits; returns (chunk_chars, total_chars, rag_top_k)."""
    chunk_chars = effective_context_chunk_chars
    total_chars = effective_context_total_chars
    chunk_override = proxy_settings_optional_int(proxy_settings, "context_chunk_chars", 64, 500_000)
    if chunk_override is not None:
        chunk_chars = chunk_override
    total_override = proxy_settings_optional_int(proxy_settings, "context_total_chars", 256, 2_000_000)
    if total_override is not None:
        total_chars = total_override
    rag_top_k = proxy_settings_optional_int(proxy_settings, "rag_top_k", 1, 256)
    return chunk_chars, total_chars, rag_top_k
