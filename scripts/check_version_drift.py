"""Check that package, runtime, and changelog versions stay in sync."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VERSION_RE = re.compile(r'^VERSION\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
PROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')
CHANGELOG_VERSION_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)


@dataclass(frozen=True)
class VersionState:
    core_version: str
    pyproject_version: str
    changelog_version: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_core_version(version_py: Path) -> str:
    text = _read_text(version_py)
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError(f"Could not find VERSION in {version_py}")
    return match.group(1)


def parse_pyproject_version(pyproject: Path) -> str:
    in_project = False
    for raw_line in _read_text(pyproject).splitlines():
        line = raw_line.strip()
        if line == "[project]":
            in_project = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project = False
            continue
        if not in_project:
            continue
        match = PROJECT_VERSION_RE.match(line)
        if match:
            return match.group(1)
    raise ValueError(f"Could not find [project].version in {pyproject}")


def parse_changelog_version(changelog: Path) -> str:
    text = _read_text(changelog)
    match = CHANGELOG_VERSION_RE.search(text)
    if not match:
        raise ValueError(f"Could not find latest changelog version in {changelog}")
    return match.group(1)


def collect_version_state(repo_root: Path = REPO_ROOT) -> VersionState:
    return VersionState(
        core_version=parse_core_version(repo_root / "Core" / "core" / "version.py"),
        pyproject_version=parse_pyproject_version(repo_root / "pyproject.toml"),
        changelog_version=parse_changelog_version(repo_root / "CHANGELOG.md"),
    )


def find_version_drift(state: VersionState) -> list[str]:
    expected = state.core_version
    issues: list[str] = []
    if state.pyproject_version != expected:
        issues.append(
            f"pyproject.toml [project].version is {state.pyproject_version}, expected {expected}"
        )
    if state.changelog_version != expected:
        issues.append(f"CHANGELOG.md latest version is {state.changelog_version}, expected {expected}")
    return issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Core/core/version.py, pyproject.toml, and CHANGELOG.md versions match."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to check. Defaults to the parent of scripts/.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        state = collect_version_state(repo_root)
    except (OSError, ValueError) as exc:
        print(f"version drift check failed: {exc}")
        return 1

    issues = find_version_drift(state)
    if issues:
        print("version drift detected:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print(f"version drift check passed: {state.core_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
