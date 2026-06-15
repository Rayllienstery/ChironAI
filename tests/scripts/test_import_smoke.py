"""Import smoke tests after packaging bootstrap (Phase 4)."""

from __future__ import annotations

import pytest


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
