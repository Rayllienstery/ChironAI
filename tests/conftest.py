"""
Pytest configuration. Ensures project root is on sys.path for domain/application imports.
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_PATH_MARKERS = {
    "api": ("api", "integration"),
    "application": ("application",),
    "config": ("config",),
    "crawler_service": ("service",),
    "docker_manager": ("docker",),
    "domain": ("domain",),
    "extensions": ("extensions",),
    "extensions_backend": ("extensions",),
    "extensions_sandbox": ("extensions", "integration"),
    "external_docs_rag": ("service", "integration"),
    "infrastructure": ("infrastructure",),
    "llm_interactor": ("extensions", "integration"),
    "llm_proxy": ("llm_proxy",),
    "md_indexer": ("service",),
    "md_ingestion_service": ("service",),
    "rag_service": ("service",),
    "scripts": ("scripts",),
    "security": ("security",),
    "web_interaction": ("web_interaction",),
    "webui": ("webui", "integration"),
}

_SLOW_TEST_NODEIDS = {
    "tests/api/test_webui_dependencies_routes.py::test_run_job_records_streaming_progress",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply stable path-based markers so local and CI test groups stay in sync."""
    del config
    for item in items:
        nodeid = item.nodeid.replace("\\", "/")
        parts = nodeid.split("/")
        group = parts[1] if len(parts) > 1 and parts[0] == "tests" else ""
        for marker in _PATH_MARKERS.get(group, ()):
            item.add_marker(getattr(pytest.mark, marker))
        if nodeid in _SLOW_TEST_NODEIDS:
            item.add_marker(pytest.mark.slow)
        else:
            item.add_marker(pytest.mark.fast)


@pytest.fixture
def tmp_path() -> Path:
    """
    Workspace-local tmp path fixture that avoids pytest's Windows ACL edge case
    in this environment.
    """
    tmp_root = Path(_ROOT) / ".tmp_test_local"
    tmp_root.mkdir(parents=True, exist_ok=True)
    path = tmp_root / f"case-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _disable_extension_background_bootstrap_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from leaking long-lived extension bootstrap threads."""
    try:
        from llm_interactor import ExtensionManager
    except Exception:
        return
    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)
