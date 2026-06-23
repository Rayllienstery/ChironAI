from __future__ import annotations

from config import (
    get_extensions_blocklist_url,
    get_extensions_local_blocklist_fallback,
    get_extensions_local_registry_fallback,
    get_extensions_registry_url,
)


def test_extensions_registry_config_defaults_to_github_with_local_fallback(monkeypatch) -> None:
    monkeypatch.delenv("CHIRONAI_EXTENSIONS_REGISTRY_URL", raising=False)
    monkeypatch.delenv("CHIRONAI_EXTENSIONS_LOCAL_REGISTRY_FALLBACK", raising=False)
    monkeypatch.delenv("CHIRONAI_EXTENSIONS_BLOCKLIST_URL", raising=False)
    monkeypatch.delenv("CHIRONAI_EXTENSIONS_LOCAL_BLOCKLIST_FALLBACK", raising=False)

    assert get_extensions_registry_url().endswith("/ChironAI-Extensions-Registry/main/extensions.json")
    assert get_extensions_local_registry_fallback() == "extensions/registry/extensions.json"
    assert get_extensions_blocklist_url().endswith("/ChironAI-Extensions-Registry/main/blocklist.json")
    assert get_extensions_local_blocklist_fallback() == "extensions/registry/blocklist.json"


def test_extensions_registry_config_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CHIRONAI_EXTENSIONS_REGISTRY_URL", "https://example.invalid/extensions.json")
    monkeypatch.setenv("CHIRONAI_EXTENSIONS_LOCAL_REGISTRY_FALLBACK", "local.json")
    monkeypatch.setenv("CHIRONAI_EXTENSIONS_BLOCKLIST_URL", "blocklist.json")
    monkeypatch.setenv("CHIRONAI_EXTENSIONS_LOCAL_BLOCKLIST_FALLBACK", "local-blocklist.json")

    assert get_extensions_registry_url() == "https://example.invalid/extensions.json"
    assert get_extensions_local_registry_fallback() == "local.json"
    assert get_extensions_blocklist_url() == "blocklist.json"
    assert get_extensions_local_blocklist_fallback() == "local-blocklist.json"
