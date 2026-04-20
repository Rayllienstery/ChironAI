from __future__ import annotations

from application.rag.proxy_settings_contract import (
    resolve_fetch_web_knowledge,
    resolve_hybrid_sparse_enabled,
    resolve_proxy_rerank_enabled,
    resolve_rag_collection,
    resolve_web_interaction_flags,
)


class _Repo:
    def __init__(self, values: dict[str, str | None]) -> None:
        self._values = values

    def get_app_setting(self, key: str) -> str | None:
        return self._values.get(key)


def test_resolve_rag_collection_prefers_request() -> None:
    repo = _Repo({"rag_collection": "app-docs"})
    value, source = resolve_rag_collection(
        request_collection="request-docs",
        settings_repo=repo,
        proxy_settings={"rag_collection": "legacy-docs"},
    )
    assert value == "request-docs"
    assert source == "request"


def test_resolve_rag_collection_uses_app_then_legacy() -> None:
    repo = _Repo({"rag_collection": "app-docs"})
    value, source = resolve_rag_collection(
        request_collection=None,
        settings_repo=repo,
        proxy_settings={"rag_collection": "legacy-docs"},
    )
    assert value == "app-docs"
    assert source == "app_settings.rag_collection"

    repo_empty = _Repo({"rag_collection": ""})
    value2, source2 = resolve_rag_collection(
        request_collection=None,
        settings_repo=repo_empty,
        proxy_settings={"rag_collection": "legacy-docs"},
    )
    assert value2 == "legacy-docs"
    assert source2 == "proxy_settings.rag_collection"


def test_resolve_proxy_rerank_enabled_prefers_proxy_settings() -> None:
    repo = _Repo({"proxy_settings": ""})
    enabled, source = resolve_proxy_rerank_enabled(
        settings_repo=repo,
        proxy_settings={"rerank_for_rag": False},
        fallback_getter=lambda: True,
    )
    assert enabled is False
    assert source == "proxy_settings.rerank_for_rag"


def test_resolve_hybrid_sparse_enabled_source_labels() -> None:
    value, source = resolve_hybrid_sparse_enabled(
        proxy_settings={"hybrid_sparse_enabled": False},
        yaml_default=True,
    )
    assert value is False
    assert source == "proxy_settings.hybrid_sparse_enabled"

    value2, source2 = resolve_hybrid_sparse_enabled(
        proxy_settings={},
        yaml_default=True,
    )
    assert value2 is True
    assert source2 == "retrieval_yaml.hybrid_sparse_enabled"


def test_resolve_fetch_web_knowledge_source_labels() -> None:
    value, source = resolve_fetch_web_knowledge(
        request_value=True,
        proxy_settings={"fetch_web_knowledge": False},
        is_autocomplete=False,
    )
    assert value is True
    assert source == "request.fetch_web_knowledge"

    value2, source2 = resolve_fetch_web_knowledge(
        request_value=None,
        proxy_settings={"fetch_web_knowledge": True},
        is_autocomplete=False,
    )
    assert value2 is True
    assert source2 == "proxy_settings.fetch_web_knowledge"

    value3, source3 = resolve_fetch_web_knowledge(
        request_value=True,
        proxy_settings={},
        is_autocomplete=True,
    )
    assert value3 is False
    assert source3 == "autocomplete_forced_off"


def test_resolve_web_interaction_flags_prefers_proxy_keys() -> None:
    flags = resolve_web_interaction_flags(
        proxy_settings={
            "web_interaction_enabled": True,
            "web_interaction_ddg_news": False,
        },
        env_ddg_news=True,
        env_fetch_page=True,
        env_wikipedia=False,
    )
    assert flags["web_interaction_enabled"]["value"] is True
    assert flags["web_interaction_enabled"]["source"] == "proxy_settings.web_interaction_enabled"
    assert flags["web_interaction_ddg_news"]["value"] is False
    assert flags["web_interaction_ddg_news"]["source"] == "proxy_settings.web_interaction_ddg_news"
    assert flags["web_interaction_fetch_page"]["value"] is True
    assert flags["web_interaction_fetch_page"]["source"] == "env.fetch_page"
