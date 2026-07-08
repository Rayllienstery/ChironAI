"""Pytest configuration. Ensures source roots are on sys.path."""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest_plugins = ["tests.api.http_fixtures"]

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CORE_ROOT = os.path.join(_ROOT, "Core")
for _path in (_ROOT, _CORE_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

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
    "tests/api/test_http_chat_completions.py::test_chat_completions_stream_returns_tool_calls_chunks",
    "tests/api/test_http_chat_completions.py::test_stream_tool_mode_returns_plain_text_when_no_tool_json",
    "tests/api/test_http_chat_completions.py::test_streaming_vision_request_preserves_native_tools_when_model_supports_them",
    "tests/api/test_http_chat_completions.py::test_streaming_vision_request_preserves_native_tools_even_when_caps_omit_tools",
    "tests/api/test_http_chat_completions.py::test_streaming_vision_request_uses_fallback_when_model_lacks_vision",
    "tests/api/test_http_chat_completions.py::test_native_tools_finalize_nudge_stays_in_initial_system_message",
    "tests/api/test_http_chat_completions.py::test_stream_trace_separates_reasoning_and_final_content_in_sse",
    "tests/api/test_http_chat_completions.py::test_chat_completions_non_stream_uses_ollama_provider_runtime",
    "tests/api/test_http_chat_completions.py::test_chat_completions_stream_uses_ollama_provider_runtime",
    "tests/api/test_http_chat_completions.py::test_stream_reasoning_only_guard_stops_visible_repeat",
    "tests/api/test_http_chat_completions.py::test_streaming_budget_exhaustion_is_visible_to_client",
}

_REAL_EXTENSION_WIRING_TESTS = frozenset(
    {
        "tests/api/test_http_extensions.py::test_create_app_syncs_extension_runtime_after_background_bootstrap",
        "tests/api/test_http_extensions.py::test_create_app_bootstraps_extension_runtime_at_wiring",
        "tests/api/test_extensions_routes.py::test_create_app_syncs_extension_runtime_after_background_bootstrap",
        "tests/api/test_extensions_routes.py::test_create_app_bootstraps_extension_runtime_at_wiring",
    }
)


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
def _reset_webui_sqlite_singletons() -> Iterator[None]:
    """Drop cached SQLite repository singletons so connections are not leaked across tests."""
    yield
    import gc

    for module_name, attr in (
        ("infrastructure.database.notifications_repository", "_notifications_repository"),
        ("infrastructure.database.session_manager", "_session_manager"),
        ("infrastructure.database.logs_repository", "_logs_repository"),
        ("infrastructure.database.settings_repository", "_settings_repository"),
        ("infrastructure.database.rag_test_runs_repository", "_rag_test_runs_repository"),
    ):
        try:
            module = __import__(module_name, fromlist=[attr])
            setattr(module, attr, None)
        except Exception:  # safe: optional infra module cleanup in teardown
            pass
    gc.collect()


@pytest.fixture(autouse=True)
def _disable_extension_background_bootstrap_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from leaking long-lived extension bootstrap threads."""
    try:
        from llm_interactor import ExtensionManager
    except Exception:
        return
    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)


@pytest.fixture(autouse=True)
def _reset_qdrant_health_monitor_between_tests() -> Iterator[None]:
    """Prevent the global Qdrant health monitor from leaking state across tests."""
    try:
        from rag_service.qdrant_health_monitor import reset_qdrant_health_monitor_for_tests
    except Exception:
        yield
        return
    reset_qdrant_health_monitor_for_tests()
    yield
    reset_qdrant_health_monitor_for_tests()
