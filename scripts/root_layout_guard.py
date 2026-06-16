"""Guardrail for top-level repository ownership.

The root may contain migration tails and project support, but new runtime
packages must be explicitly classified before they are added.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RootEntry:
    owner: str
    kind: str
    runtime_source: bool = False


ALLOWED_ROOT_DIRECTORIES: dict[str, RootEntry] = {
    ".cursor": RootEntry("project support", "editor metadata"),
    ".git": RootEntry("project support", "VCS metadata"),
    ".github": RootEntry("project support", "CI metadata"),
    ".import_linter_cache": RootEntry("project support", "tool cache"),
    ".kilo": RootEntry("project support", "agent metadata"),
    ".ruff_cache": RootEntry("project support", "tool cache"),
    ".tmp_openwebui_data": RootEntry("temporary", "local runtime data"),
    ".tmp_test_local": RootEntry("temporary", "local test data"),
    ".vscode": RootEntry("project support", "editor metadata"),
    "chironai.egg-info": RootEntry("project support", "packaging metadata"),
    "Core": RootEntry("Core", "application host container", runtime_source=True),
    "CoreModules": RootEntry("CoreModules", "reusable modules and applications", runtime_source=True),
    "docs": RootEntry("project support", "architecture and runbooks"),
    "extensions": RootEntry("extensions", "extension payloads", runtime_source=True),
    "logs": RootEntry("runtime data", "local logs and databases"),
    "rag_tests": RootEntry("project support", "RAG evaluation fixtures"),
    "reports": RootEntry("project support", "generated reports"),
    "scripts": RootEntry("project support", "repo tooling"),
    "tests": RootEntry("project support", "test suite"),
    "tmp": RootEntry("temporary", "scratch and cloned dependency worktrees"),
    "WebUI": RootEntry("runtime data", "runtime/data folder, not frontend source"),
}


def _looks_like_python_runtime_package(path: Path) -> bool:
    if (path / "__init__.py").exists():
        return True
    return any(child.suffix == ".py" for child in path.iterdir() if child.is_file())


def find_root_layout_violations(root: Path) -> list[str]:
    violations: list[str] = []
    existing_names = {entry.name for entry in root.iterdir() if entry.is_dir()}
    for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_dir():
            continue
        allowed = ALLOWED_ROOT_DIRECTORIES.get(entry.name)
        if allowed is None:
            message = f"{entry.name}: top-level directory is not classified in ALLOWED_ROOT_DIRECTORIES"
            if _looks_like_python_runtime_package(entry):
                message += " and looks like a Python runtime package"
            violations.append(message)
    legacy_tails = ("api", "application", "config", "core", "domain", "infrastructure", "modules", "prompts")
    for name in legacy_tails:
        if name in existing_names:
            if name == "modules":
                violations.append(f"{name}: Phase 2 moved host-owned services under Core/modules/")
            elif name == "prompts":
                violations.append(f"{name}: Phase 3 moved prompt templates under Core/modules/prompts_manager/")
            else:
                violations.append(f"{name}: Phase 1 moved this host runtime package under Core/")
    return violations


def render_ownership_table() -> str:
    rows = ["| Root folder | Owner | Classification |", "|-------------|-------|----------------|"]
    for name, entry in sorted(ALLOWED_ROOT_DIRECTORIES.items(), key=lambda item: item[0].lower()):
        rows.append(f"| `{name}/` | {entry.owner} | {entry.kind} |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate top-level repository ownership.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--print-table", action="store_true", help="Print the documented ownership table.")
    args = parser.parse_args(argv)

    if args.print_table:
        print(render_ownership_table())
        return 0

    violations = find_root_layout_violations(args.root)
    if violations:
        print("Unclassified root directories found:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
