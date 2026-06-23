from __future__ import annotations

import threading
from pathlib import Path

from llm_interactor.discovery import LoadedExtension
from llm_interactor.manager_extension_tabs import (
    ExtensionTabCacheEntry,
    build_extension_descriptor,
    build_extension_tab_payload,
    extension_descriptor_row,
    invalidate_extension_tab_cache_entries,
    loaded_tab_status_overlay,
    mark_tab_cache_stale_entries,
    tab_load_state,
)
from llm_interactor.manifest import EXTENSION_API_VERSION, ExtensionManifest


class _TabProvider:
    sandbox_status = "ready"
    sandbox_error = ""

    def get_tab_descriptor(self, *, runtime=None) -> dict[str, object]:
        return {"id": "custom-tab", "title": "Custom", "order": 2}

    def get_tab_payload(self, *, runtime=None) -> dict[str, object]:
        return {
            "extension_id": "spoof",
            "title": "Spoof",
            "schema": {"pages": [{"id": "main"}]},
        }


def test_tab_load_state_returns_missing_defaults() -> None:
    state = tab_load_state({}, threading.RLock(), "missing-ext")
    assert state["status"] == "missing"
    assert state["job_id"] == ""


def test_mark_tab_cache_stale_entries_marks_ready_rows() -> None:
    cache = {"ext-a": ExtensionTabCacheEntry(status="ready")}
    mark_tab_cache_stale_entries(cache)
    assert cache["ext-a"].status == "stale"


def test_invalidate_extension_tab_cache_entries_pops_empty_rows() -> None:
    cache = {"ext-a": ExtensionTabCacheEntry(status="missing")}
    invalidate_extension_tab_cache_entries(cache)
    assert "ext-a" not in cache


def test_extension_descriptor_row_builds_asset_url(tmp_path: Path) -> None:
    manifest = ExtensionManifest(
        id="sample-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="ui_extension",
        title="Sample",
        icon="icons/logo.svg",
    )
    loaded = LoadedExtension(
        manifest=manifest,
        source_dir=tmp_path,
        provider=_TabProvider(),
    )
    row = extension_descriptor_row(
        loaded,
        {"id": "custom-tab", "title": "Custom"},
        asset_url=lambda ext_id, icon: f"/assets/{ext_id}/{icon}",
    )
    assert row["icon_url"] == "/assets/sample-ext/icons/logo.svg"
    assert row["extension_id"] == "sample-ext"


def test_build_extension_tab_payload_strips_protected_keys(tmp_path: Path) -> None:
    manifest = ExtensionManifest(
        id="sample-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="ui_extension",
        title="Sample",
    )
    loaded = LoadedExtension(
        manifest=manifest,
        source_dir=tmp_path,
        provider=_TabProvider(),
    )
    payload = build_extension_tab_payload(
        loaded,
        None,
        asset_url=lambda ext_id, icon: f"/assets/{ext_id}",
    )
    assert payload["extension_id"] == "sample-ext"
    assert payload["title"] == "Sample"
    assert payload["schema"]["pages"][0]["id"] == "main"


def test_build_extension_descriptor_returns_none_without_hook(tmp_path: Path) -> None:
    manifest = ExtensionManifest(
        id="sample-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="ui_extension",
        title="Sample",
    )
    loaded = LoadedExtension(
        manifest=manifest,
        source_dir=tmp_path,
        provider=object(),
    )
    assert build_extension_descriptor(loaded, None, asset_url=lambda *_: "") is None


def test_loaded_tab_status_overlay_warns_on_manual_stop() -> None:
    manifest = ExtensionManifest(
        id="sample-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="ui_extension",
        title="Sample",
    )
    provider = _TabProvider()
    provider.sandbox_status = "manual_stop"
    loaded = LoadedExtension(
        manifest=manifest,
        source_dir=Path("."),
        provider=provider,
    )
    overlay = loaded_tab_status_overlay(loaded)
    assert overlay is not None
    assert overlay["tone"] == "warning"
    assert "manual restart" in overlay["message"].lower()
