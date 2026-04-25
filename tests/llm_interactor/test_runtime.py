from __future__ import annotations

from pathlib import Path

import pytest

from llm_interactor import (
    EXTENSION_API_VERSION,
    ExtensionManager,
    ExtensionRegistryClient,
    LLMRequest,
    LLMResponse,
    LLMRuntime,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderHostContext,
    ProviderRegistry,
)


class _StubProvider:
    def __init__(self, provider_id: str = "stub") -> None:
        self._provider_id = provider_id

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id=self._provider_id,
            extension_id="stub-ext",
            title="Stub",
            capabilities=ProviderCapabilities(),
        )

    def list_models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                id="model-a",
                provider_id=self._provider_id,
                label="Model A",
                capabilities=ProviderCapabilities(),
            )
        ]

    def invoke(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(provider_id=self._provider_id, model=request.model, text="ok")

    def stream_invoke(self, request: LLMRequest):
        yield from ()

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self._provider_id, ok=True, status="ok")


def test_runtime_without_provider_raises_clear_error() -> None:
    runtime = LLMRuntime(ProviderRegistry())
    with pytest.raises(RuntimeError, match="no provider configured"):
        runtime.invoke(LLMRequest(model="m"))


def test_provider_registry_rejects_duplicate_ids() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider("dup"))
    with pytest.raises(ValueError, match="duplicate provider id"):
        registry.register(_StubProvider("dup"))


def test_extension_manager_bootstraps_builtin_ollama(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
    )
    bootstrap = manager.bootstrap_runtime()
    installed = manager.installed_extensions()
    assert bootstrap.runtime is not None
    assert any(item["id"] == "ollama-provider" for item in installed)


def test_registry_client_reads_local_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    client = ExtensionRegistryClient(project_root=root)
    rows = client.load()
    assert any(row["id"] == "ollama-provider" for row in rows)
