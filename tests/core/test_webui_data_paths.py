from __future__ import annotations

import shutil
from pathlib import Path

from core.webui_data_paths import (
    default_webui_data_dir,
    legacy_webui_data_dir,
    resolve_webui_data_dir,
)


def test_default_webui_data_dir_is_under_core(tmp_path: Path) -> None:
    assert default_webui_data_dir(tmp_path) == tmp_path / "Core" / "data" / "webui"


def test_resolve_webui_data_dir_honors_env_override(tmp_path: Path, monkeypatch) -> None:
    custom = tmp_path / "custom-data"
    custom.mkdir()
    monkeypatch.setenv("CHIRONAI_WEBUI_DIR", str(custom))

    assert resolve_webui_data_dir(tmp_path) == custom.resolve()


def test_resolve_webui_data_dir_migrates_legacy_root_webui(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHIRONAI_WEBUI_DIR", raising=False)
    legacy = legacy_webui_data_dir(tmp_path)
    legacy.mkdir()
    (legacy / "rag_sources").mkdir()
    (legacy / "last_collection.txt").write_text("demo", encoding="utf-8")

    target = resolve_webui_data_dir(tmp_path)

    assert target == default_webui_data_dir(tmp_path)
    assert (target / "rag_sources").is_dir()
    assert (target / "last_collection.txt").read_text(encoding="utf-8") == "demo"
    assert (target / ".migrated_from_root_webui").is_file()
    assert not legacy.exists()


def test_resolve_webui_data_dir_skips_migration_when_marker_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHIRONAI_WEBUI_DIR", raising=False)
    legacy = legacy_webui_data_dir(tmp_path)
    legacy.mkdir()
    (legacy / "orphan.txt").write_text("stay", encoding="utf-8")

    target = default_webui_data_dir(tmp_path)
    target.mkdir(parents=True)
    (target / ".migrated_from_root_webui").write_text("legacy=WebUI\n", encoding="utf-8")

    assert resolve_webui_data_dir(tmp_path) == target
    assert (legacy / "orphan.txt").read_text(encoding="utf-8") == "stay"


def test_resolve_webui_data_dir_does_not_overwrite_existing_targets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHIRONAI_WEBUI_DIR", raising=False)
    legacy = legacy_webui_data_dir(tmp_path)
    legacy.mkdir()
    (legacy / "last_collection.txt").write_text("legacy", encoding="utf-8")

    target = default_webui_data_dir(tmp_path)
    target.mkdir(parents=True)
    (target / "last_collection.txt").write_text("current", encoding="utf-8")

    assert resolve_webui_data_dir(tmp_path) == target
    assert (target / "last_collection.txt").read_text(encoding="utf-8") == "current"
    assert (legacy / "last_collection.txt").read_text(encoding="utf-8") == "legacy"

    shutil.rmtree(legacy)
