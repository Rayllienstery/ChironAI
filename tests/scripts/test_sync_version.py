from __future__ import annotations

from pathlib import Path

from scripts import check_version_drift, sync_version


def _write_version_repo(root: Path, version: str = "1.2.3") -> None:
    version_dir = root / "Core" / "core"
    version_dir.mkdir(parents=True)
    (version_dir / "version.py").write_text(f'VERSION = "{version}"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "sample"\n'
        f'version = "{version}"\n\n'
        "[tool.commitizen]\n"
        'name = "cz_conventional_commits"\n'
        f'version = "{version}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\nAll notable changes.\n\n## [{version}] - 2026-06-18\n### Changed\n- Existing.\n",
        encoding="utf-8",
    )


def test_bump_version_increments_semver() -> None:
    assert sync_version.bump_version("1.2.3", "patch") == "1.2.4"
    assert sync_version.bump_version("1.2.3", "minor") == "1.3.0"
    assert sync_version.bump_version("1.2.3", "major") == "2.0.0"


def test_apply_native_bump_updates_all_version_sources(tmp_path: Path) -> None:
    _write_version_repo(tmp_path)
    plan = sync_version.build_plan(
        tmp_path,
        increment="patch",
        explicit_version=None,
        message="Added version automation.",
    )

    sync_version.apply_native_bump(tmp_path, plan)

    state = check_version_drift.collect_version_state(tmp_path)
    assert state == check_version_drift.VersionState(
        core_version="1.2.4",
        pyproject_version="1.2.4",
        changelog_version="1.2.4",
        commitizen_version="1.2.4",
    )
    assert "Added version automation." in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")


def test_build_plan_rejects_existing_drift(tmp_path: Path) -> None:
    _write_version_repo(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8").replace('version = "1.2.3"', 'version = "1.2.2"', 1), encoding="utf-8")

    try:
        sync_version.build_plan(
            tmp_path,
            increment="patch",
            explicit_version=None,
            message="Added version automation.",
        )
    except RuntimeError as exc:
        assert "version drift" in str(exc)
    else:
        raise AssertionError("Expected drift to block the bump")
