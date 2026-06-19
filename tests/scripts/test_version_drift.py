from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import check_version_drift

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_version_repo(root: Path, *, core: str, pyproject: str, changelog: str) -> None:
    version_dir = root / "Core" / "core"
    version_dir.mkdir(parents=True)
    (version_dir / "version.py").write_text(f'VERSION = "{core}"\n', encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[build-system]\nrequires = []\n\n[project]\nname = "sample"\nversion = "{pyproject}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [{changelog}] - 2026-06-18\n### Fixed\n- Sample.\n",
        encoding="utf-8",
    )


def test_collect_version_state_reads_all_sources(tmp_path: Path) -> None:
    _write_version_repo(tmp_path, core="1.2.3", pyproject="1.2.3", changelog="1.2.3")

    state = check_version_drift.collect_version_state(tmp_path)

    assert state == check_version_drift.VersionState(
        core_version="1.2.3",
        pyproject_version="1.2.3",
        changelog_version="1.2.3",
    )
    assert check_version_drift.find_version_drift(state) == []


def test_find_version_drift_reports_mismatches() -> None:
    state = check_version_drift.VersionState(
        core_version="1.2.3",
        pyproject_version="1.2.2",
        changelog_version="1.2.1",
    )

    issues = check_version_drift.find_version_drift(state)

    assert "pyproject.toml" in issues[0]
    assert "CHANGELOG.md" in issues[1]


def test_check_version_drift_cli_fails_on_drift(tmp_path: Path) -> None:
    _write_version_repo(tmp_path, core="1.2.3", pyproject="1.2.2", changelog="1.2.3")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_version_drift.py"), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "version drift detected" in result.stdout
