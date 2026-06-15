from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from llm_proxy.chat_completions_rag_prep import (
    apply_proxy_context_char_limits,
    build_framework_name_to_collection_map,
    resolve_framework_collection_ttl_days,
    resolve_project_fresh_collections,
)

from application.rag.collection_freshness import check_collection_freshness


def _cfg(*, keywords: list[str], collection: str, source_id: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        trigger_keywords=keywords,
        collection_name=collection,
        external_source_id=source_id,
    )


def test_build_framework_name_to_collection_map() -> None:
    configs = [
        _cfg(keywords=["Alamofire", "AFNetworking"], collection="ios-networking"),
        _cfg(keywords=[], collection="swiftui", source_id="SwiftUI"),
    ]
    mapping = build_framework_name_to_collection_map(configs)
    assert mapping["alamofire"] == "ios-networking"
    assert mapping["afnetworking"] == "ios-networking"
    assert mapping["swiftui"] == "swiftui"


def test_resolve_framework_collection_ttl_days_from_settings() -> None:
    class Repo:
        def get_app_setting(self, key: str) -> str | None:
            if key == "framework_collection_ttl_days":
                return "14"
            return None

    assert resolve_framework_collection_ttl_days(Repo(), default_ttl_days=90) == 14
    assert resolve_framework_collection_ttl_days(None, default_ttl_days=90) == 90


def test_resolve_project_fresh_collections_splits_fresh_and_stale() -> None:
    fresh_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    stale_at = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()

    class Repo:
        def get_collection_meta(self, name: str) -> dict[str, str] | None:
            if name == "fresh-coll":
                return {"collection_name": name, "last_refreshed_at": fresh_at}
            if name == "stale-coll":
                return {"collection_name": name, "last_refreshed_at": stale_at}
            return None

    mapping = {"alamofire": "fresh-coll", "swiftui": "stale-coll"}
    frameworks = [{"name": "Alamofire"}, {"name": "SwiftUI"}, {"name": "Unknown"}]
    fresh, needs_refresh = resolve_project_fresh_collections(
        frameworks,
        name_to_collection=mapping,
        settings_repo=Repo(),
        check_collection_freshness=check_collection_freshness,
        default_ttl_days=30,
    )
    assert fresh == {"fresh-coll"}
    assert needs_refresh == [("swiftui", "stale-coll")]


def test_apply_proxy_context_char_limits_overrides() -> None:
    chunk, total, top_k = apply_proxy_context_char_limits(
        {"context_chunk_chars": 4096, "context_total_chars": 8192, "rag_top_k": 12},
        effective_context_chunk_chars=1024,
        effective_context_total_chars=2048,
    )
    assert chunk == 4096
    assert total == 8192
    assert top_k == 12


def test_apply_proxy_context_char_limits_keeps_defaults_when_unset() -> None:
    chunk, total, top_k = apply_proxy_context_char_limits(
        {},
        effective_context_chunk_chars=1024,
        effective_context_total_chars=2048,
    )
    assert chunk == 1024
    assert total == 2048
    assert top_k is None
