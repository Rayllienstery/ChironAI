"""
Unified settings resolver for proxy/RAG configuration (Track B / Phase 1).

Single entry point for call sites that previously duplicated JSON parsing
and precedence logic. Delegates to ``proxy_settings_contract`` primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_fetch_web_knowledge,
    resolve_hybrid_sparse_enabled,
    resolve_proxy_rerank_enabled,
    resolve_rag_collection,
    resolve_web_interaction_flags,
)

# Legacy proxy_settings keys exercised by contract tests and migration paths.
LEGACY_PROXY_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "rag_collection",
        "rerank_for_rag",
        "hybrid_sparse_enabled",
        "fetch_web_knowledge",
        "prompt_name",
        "web_interaction_enabled",
        "web_interaction_on_keywords",
        "web_interaction_on_low_confidence_framework",
        "web_interaction_ddg_news",
        "web_interaction_fetch_page",
        "web_interaction_wikipedia",
    }
)


@dataclass(frozen=True)
class ResolvedSetting:
    """A resolved boolean/string setting with explicit provenance."""

    value: Any
    source: str


@dataclass
class ProxyRagSettings:
    """Snapshot of proxy/RAG settings for a single request or operation."""

    proxy_settings: dict[str, Any]
    rag_collection: ResolvedSetting
    rerank_enabled: ResolvedSetting
    hybrid_sparse_enabled: ResolvedSetting

    @classmethod
    def from_repository(
        cls,
        settings_repo: Any,
        *,
        request_collection: str | None = None,
        rerank_fallback: Callable[[], bool] | None = None,
        yaml_hybrid_default: bool | None = None,
    ) -> ProxyRagSettings:
        proxy_settings = load_proxy_settings(settings_repo)
        coll_val, coll_src = resolve_rag_collection(
            request_collection=request_collection,
            settings_repo=settings_repo,
            proxy_settings=proxy_settings,
        )
        rerank_val, rerank_src = resolve_proxy_rerank_enabled(
            settings_repo=settings_repo,
            proxy_settings=proxy_settings,
            fallback_getter=rerank_fallback,
        )
        hybrid_val, hybrid_src = resolve_hybrid_sparse_enabled(
            proxy_settings=proxy_settings,
            yaml_default=yaml_hybrid_default,
        )
        return cls(
            proxy_settings=proxy_settings,
            rag_collection=ResolvedSetting(coll_val, coll_src),
            rerank_enabled=ResolvedSetting(rerank_val, rerank_src),
            hybrid_sparse_enabled=ResolvedSetting(hybrid_val, hybrid_src),
        )


def resolve_all_proxy_settings(
    settings_repo: Any,
    *,
    request_collection: str | None = None,
    request_fetch_web_knowledge: Any = None,
    is_autocomplete: bool = False,
    rerank_fallback: Callable[[], bool] | None = None,
    env_ddg_news: bool = False,
    env_fetch_page: bool = False,
    env_wikipedia: bool = False,
) -> dict[str, Any]:
    """Return a dict of resolved values + sources for diagnostics and tests."""
    snapshot = ProxyRagSettings.from_repository(
        settings_repo,
        request_collection=request_collection,
        rerank_fallback=rerank_fallback,
    )
    fetch_val, fetch_src = resolve_fetch_web_knowledge(
        request_value=request_fetch_web_knowledge,
        proxy_settings=snapshot.proxy_settings,
        is_autocomplete=is_autocomplete,
    )
    web_flags = resolve_web_interaction_flags(
        proxy_settings=snapshot.proxy_settings,
        env_ddg_news=env_ddg_news,
        env_fetch_page=env_fetch_page,
        env_wikipedia=env_wikipedia,
    )
    return {
        "rag_collection": {"value": snapshot.rag_collection.value, "source": snapshot.rag_collection.source},
        "rerank_for_rag": {
            "value": snapshot.rerank_enabled.value,
            "source": snapshot.rerank_enabled.source,
        },
        "hybrid_sparse_enabled": {
            "value": snapshot.hybrid_sparse_enabled.value,
            "source": snapshot.hybrid_sparse_enabled.source,
        },
        "fetch_web_knowledge": {"value": fetch_val, "source": fetch_src},
        "web_interaction": web_flags,
        "proxy_settings_keys": sorted(snapshot.proxy_settings.keys()),
    }


__all__ = [
    "LEGACY_PROXY_SETTING_KEYS",
    "ProxyRagSettings",
    "ResolvedSetting",
    "load_proxy_settings",
    "resolve_all_proxy_settings",
    "resolve_fetch_web_knowledge",
    "resolve_hybrid_sparse_enabled",
    "resolve_proxy_rerank_enabled",
    "resolve_rag_collection",
    "resolve_web_interaction_flags",
]
