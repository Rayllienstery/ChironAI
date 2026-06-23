"""Synchronize project version files and CHANGELOG entries."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import check_version_drift

SEMVER_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


@dataclass(frozen=True)
class BumpPlan:
    current_version: str
    next_version: str
    increment: str
    message: str


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(version)
    if not match:
        raise ValueError(f"Unsupported version format: {version!r}")
    return (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))


def bump_version(version: str, increment: str) -> str:
    major, minor, patch = parse_semver(version)
    if increment == "major":
        return f"{major + 1}.0.0"
    if increment == "minor":
        return f"{major}.{minor + 1}.0"
    if increment == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported increment: {increment}")


def build_plan(
    repo_root: Path,
    *,
    increment: str,
    explicit_version: str | None,
    message: str,
) -> BumpPlan:
    state = check_version_drift.collect_version_state(repo_root)
    issues = check_version_drift.find_version_drift(state)
    if issues:
        details = "\n".join(f"- {issue}" for issue in issues)
        raise RuntimeError(f"Cannot bump while version drift exists:\n{details}")

    next_version = explicit_version or bump_version(state.core_version, increment)
    parse_semver(next_version)
    if next_version == state.core_version:
        raise RuntimeError(f"Next version must differ from current version {state.core_version}")

    return BumpPlan(
        current_version=state.core_version,
        next_version=next_version,
        increment=increment,
        message=message,
    )


def replace_core_version(text: str, version: str) -> str:
    updated, count = check_version_drift.VERSION_RE.subn(f'VERSION = "{version}"', text, count=1)
    if count != 1:
        raise ValueError("Could not replace VERSION in Core/core/version.py")
    return updated


def replace_section_version(text: str, section: str, version: str) -> str:
    lines = text.splitlines(keepends=True)
    in_section = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section:
            in_section = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = False
            continue
        if in_section and check_version_drift.PROJECT_VERSION_RE.match(stripped):
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            prefix = line[: len(line) - len(line.lstrip())]
            lines[index] = f'{prefix}version = "{version}"{newline}'
            replaced = True
            break
    if not replaced:
        raise ValueError(f"Could not replace version in {section}")
    return "".join(lines)


def insert_changelog_entry(text: str, version: str, message: str) -> str:
    if re.search(rf"^## \[{re.escape(version)}\]", text, flags=re.MULTILINE):
        raise ValueError(f"CHANGELOG.md already has an entry for {version}")

    entry = f"## [{version}] - {date.today().isoformat()}\n### Changed\n- {message}\n\n"
    first_entry = re.search(r"^## \[", text, flags=re.MULTILINE)
    if not first_entry:
        return text.rstrip() + "\n\n" + entry.rstrip() + "\n"
    return text[: first_entry.start()] + entry + text[first_entry.start() :]


def apply_native_bump(repo_root: Path, plan: BumpPlan) -> None:
    version_py = repo_root / "Core" / "core" / "version.py"
    pyproject = repo_root / "pyproject.toml"
    changelog = repo_root / "CHANGELOG.md"

    version_py.write_text(
        replace_core_version(version_py.read_text(encoding="utf-8"), plan.next_version),
        encoding="utf-8",
    )
    pyproject_text = pyproject.read_text(encoding="utf-8")
    pyproject_text = replace_section_version(pyproject_text, "[project]", plan.next_version)
    pyproject_text = replace_section_version(pyproject_text, "[tool.commitizen]", plan.next_version)
    pyproject.write_text(pyproject_text, encoding="utf-8")
    changelog.write_text(
        insert_changelog_entry(changelog.read_text(encoding="utf-8"), plan.next_version, plan.message),
        encoding="utf-8",
    )


def run_commitizen_bump(plan: BumpPlan) -> int:
    executable = shutil.which("cz")
    if executable is None:
        print("commitizen executable not found; use native sync or install the dev dependency.", file=sys.stderr)
        return 1
    command = [executable, "bump", "--yes", "--increment", plan.increment]
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def print_plan(plan: BumpPlan) -> None:
    cz_status = "available" if shutil.which("cz") else "not installed; native sync is available"
    print(f"current version: {plan.current_version}")
    print(f"next version: {plan.next_version}")
    print(f"increment: {plan.increment}")
    print("version files:")
    print("- Core/core/version.py:VERSION")
    print("- pyproject.toml:[project].version")
    print("- pyproject.toml:[tool.commitizen].version")
    print("- CHANGELOG.md latest entry")
    print(f"commitizen: {cz_status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Core/core/version.py, pyproject.toml, and CHANGELOG.md."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="Show the next bump without writing files.")
    parser.add_argument("--use-cz", action="store_true", help="Delegate the bump to commitizen's cz executable.")
    parser.add_argument("--version", help="Set an explicit next version instead of incrementing.")
    parser.add_argument("--increment", choices=["patch", "minor", "major"], default="patch")
    parser.add_argument(
        "--message",
        default="Synchronized project version files and changelog automation.",
        help="CHANGELOG bullet used by the native bump mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        plan = build_plan(
            repo_root,
            increment=args.increment,
            explicit_version=args.version,
            message=args.message,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"sync version failed: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print_plan(plan)
        return 0

    if args.use_cz:
        return run_commitizen_bump(plan)

    try:
        apply_native_bump(repo_root, plan)
        state = check_version_drift.collect_version_state(repo_root)
        issues = check_version_drift.find_version_drift(state)
    except (OSError, ValueError) as exc:
        print(f"sync version failed: {exc}", file=sys.stderr)
        return 1

    if issues:
        print("version drift detected after bump:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print(f"version synchronized: {plan.current_version} -> {plan.next_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
