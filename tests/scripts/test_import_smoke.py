"""Import smoke tests after packaging bootstrap (Phase 4)."""

from __future__ import annotations

import importlib

import pytest

_RUNTIME_PACKAGES = (
    "api",
    "application",
    "config",
    "core",
    "domain",
    "infrastructure",
    "webui_backend",
    "extensions_backend",
    "crawler_service",
    "llm_proxy",
    "rag_service",
    "error_manager",
    "external_docs_rag",
    "chironai_security",
    "extensions_sandbox",
    "extensions_host",
    "prompts_manager",
    "docker_manager",
)


@pytest.mark.fast
@pytest.mark.scripts
@pytest.mark.parametrize("package_name", _RUNTIME_PACKAGES)
def test_runtime_package_importable(package_name: str) -> None:
    module = importlib.import_module(package_name)
    assert module is not None


@pytest.mark.fast
@pytest.mark.scripts
def test_core_contracts_importable() -> None:
    from core.contracts.webui_api import WEBUI_URL_PREFIX

    assert WEBUI_URL_PREFIX == "/api/webui"


@pytest.mark.fast
@pytest.mark.scripts
def test_settings_resolver_importable() -> None:
    from application.rag.settings_resolver import ProxyRagSettings, resolve_all_proxy_settings

    assert ProxyRagSettings is not None
    assert callable(resolve_all_proxy_settings)


@pytest.mark.fast
@pytest.mark.scripts
def test_bootstrap_paths_idempotent() -> None:
    from core.bootstrap.import_paths import ensure_webui_runtime_paths
    from webui_backend.paths import project_root

    ensure_webui_runtime_paths(project_root())
    ensure_webui_runtime_paths(project_root())


@pytest.mark.fast
@pytest.mark.scripts
def test_chironai_console_script_registered() -> None:
    import importlib.metadata as metadata

    entry_points = {ep.name for ep in metadata.entry_points(group="console_scripts")}
    assert "chironai" in entry_points
