from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from application.custom_openai_providers import upsert_custom_openai_provider
from application.host_provider_sync import sync_custom_openai_providers
from application.openai_compatible_provider import OpenAICompatibleProvider


class _MemSettingsRepo:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_app_setting(self, key: str) -> str | None:
        return self._data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self._data[key] = value


class _Registry:
    def __init__(self) -> None:
        self._providers: dict[str, object] = {}

    def providers(self):
        return list(self._providers.values())

    def get(self, provider_id: str):
        return self._providers.get(provider_id)

    def register(self, provider: object) -> None:
        self._providers[provider.describe().id] = provider

    def replace(self, provider: object) -> None:
        self._providers[provider.describe().id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)


def test_sync_custom_openai_providers_registers_enabled_records() -> None:
    repo = _MemSettingsRepo()
    upsert_custom_openai_provider(
        repo,
        provider_id="my-gateway",
        display_name="My Gateway",
        base_url="https://api.example.com/v1",
        api_key="sk-test-key",
        manual_models=["gpt-4o-mini"],
    )
    registry = _Registry()

    registered = sync_custom_openai_providers(registry, repo)

    assert registered == ["my-gateway"]
    provider = registry.get("my-gateway")
    assert provider is not None
    assert provider.describe().id == "my-gateway"
    assert provider.describe().metadata["source"] == "custom_openai"


def test_sync_custom_openai_providers_removes_stale_custom_providers() -> None:
    repo = _MemSettingsRepo()
    registry = _Registry()
    stale = OpenAICompatibleProvider(
        {
            "id": "stale-gateway",
            "display_name": "Stale",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-stale",
        }
    )
    registry.register(stale)

    registered = sync_custom_openai_providers(registry, repo)

    assert registered == []
    assert registry.get("stale-gateway") is None


def test_sync_skips_disabled_or_missing_api_key() -> None:
    repo = _MemSettingsRepo()
    upsert_custom_openai_provider(
        repo,
        provider_id="disabled-gateway",
        display_name="Disabled",
        base_url="https://api.example.com/v1",
        api_key="sk-test-key",
        enabled=False,
    )
    registry = _Registry()

    assert sync_custom_openai_providers(registry, repo) == []
