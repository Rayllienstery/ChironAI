from __future__ import annotations

from pathlib import Path

from llm_interactor.discovery import FailedExtension
from llm_interactor.manager_provider_catalog import (
    build_provider_catalog,
    provider_rows_from_runtime,
    sandbox_diagnostics,
)
from llm_interactor.manifest import ExtensionManifest

from llm_interactor import (
    EXTENSION_API_VERSION,
    LLMRequest,
    LLMResponse,
    LLMRuntime,
    LoadedExtension,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderRegistry,
)


class _StubProvider:
    sandboxed = True
    sandbox_pid = 42
    sandbox_status = "ready"
    sandbox_error = ""
    sandbox_last_error = ""
    sandbox_restart_count = 1
    sandbox_blocked = False
    sandbox_manual_restart_required = False

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="stub",
            extension_id="stub-ext",
            title="Stub",
            icon="icon.svg",
            capabilities=ProviderCapabilities(chat=True),
        )

    def list_models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                id="model-a",
                provider_id="stub",
                label="Model A",
                capabilities=ProviderCapabilities(),
            )
        ]

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id="stub", ok=True, status="ok")

    def invoke(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(provider_id="stub", model=request.model, text="ok")

    def stream_invoke(self, request: LLMRequest):
        yield from ()


def test_sandbox_diagnostics_from_loaded_extension(tmp_path: Path) -> None:
    manifest = ExtensionManifest(
        id="stub-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="llm_provider",
        title="Stub",
    )
    loaded = LoadedExtension(
        manifest=manifest,
        source_dir=tmp_path / "stub-ext",
        provider=_StubProvider(),
        sandboxed=True,
    )
    diag = sandbox_diagnostics(loaded)
    assert diag["sandboxed"] is True
    assert diag["sandbox_pid"] == 42
    assert diag["sandbox_can_restart"] is True


def test_sandbox_diagnostics_from_failed_extension(tmp_path: Path) -> None:
    failed = FailedExtension(
        extension_id="stub-ext",
        source_dir=tmp_path / "stub-ext",
        error="boom",
        sandbox_status="blocked",
        sandbox_error="worker blocked",
    )
    diag = sandbox_diagnostics(None, failed)
    assert diag["sandbox_status"] == "blocked"
    assert diag["sandbox_manual_restart_required"] is True


def test_provider_rows_from_runtime_and_catalog_filter() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider())
    runtime = LLMRuntime(registry)
    rows = provider_rows_from_runtime(
        runtime,
        asset_url=lambda ext_id, icon: f"/assets/{ext_id}/{icon}",
    )
    assert len(rows) == 1
    assert rows[0]["provider_id"] == "stub"
    assert rows[0]["icon_url"] == "/assets/stub-ext/icon.svg"

    catalog = build_provider_catalog(rows, capability="chat")
    assert len(catalog["providers"]) == 1
    assert catalog["models"][0]["id"] == "model-a"

    empty = build_provider_catalog(rows, capability="embed")
    assert empty["providers"] == []
    assert empty["models"] == []
