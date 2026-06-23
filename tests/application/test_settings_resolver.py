"""Contract tests for unified settings resolver (Phase 1 / Track B)."""

from __future__ import annotations

from application.rag.settings_resolver import (
    LEGACY_PROXY_SETTING_KEYS,
    ProxyRagSettings,
    resolve_all_proxy_settings,
)


class _Repo:
    def __init__(self, values: dict[str, str | None]) -> None:
        self._values = values

    def get_app_setting(self, key: str) -> str | None:
        return self._values.get(key)


def test_legacy_proxy_setting_keys_cover_contract_surface() -> None:
    assert "rag_collection" in LEGACY_PROXY_SETTING_KEYS
    assert "rerank_for_rag" in LEGACY_PROXY_SETTING_KEYS
    assert "hybrid_sparse_enabled" in LEGACY_PROXY_SETTING_KEYS
    assert len(LEGACY_PROXY_SETTING_KEYS) >= 10


def test_proxy_rag_settings_from_repository_prefers_request_collection() -> None:
    repo = _Repo(
        {
            "rag_collection": "app-coll",
            "proxy_settings": '{"rag_collection": "legacy-coll", "rerank_for_rag": true}',
        }
    )
    snapshot = ProxyRagSettings.from_repository(repo, request_collection="req-coll")
    assert snapshot.rag_collection.value == "req-coll"
    assert snapshot.rag_collection.source == "request"
    assert snapshot.rerank_enabled.value is True
    assert snapshot.rerank_enabled.source == "proxy_settings.rerank_for_rag"


def test_resolve_all_proxy_settings_returns_sources() -> None:
    repo = _Repo(
        {
            "proxy_settings": '{"fetch_web_knowledge": true, "web_interaction_enabled": true}',
        }
    )
    resolved = resolve_all_proxy_settings(
        repo,
        request_fetch_web_knowledge=False,
        env_ddg_news=True,
    )
    assert resolved["fetch_web_knowledge"]["source"] == "request.fetch_web_knowledge"
    assert resolved["fetch_web_knowledge"]["value"] is False
    assert resolved["web_interaction"]["web_interaction_enabled"]["value"] is True
    assert "fetch_web_knowledge" in LEGACY_PROXY_SETTING_KEYS
