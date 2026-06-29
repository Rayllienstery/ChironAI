from __future__ import annotations

from pathlib import Path

from scripts.root_layout_guard import ALLOWED_ROOT_DIRECTORIES, find_root_layout_violations, render_ownership_table


def test_current_root_directories_are_classified() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert find_root_layout_violations(repo_root) == []


def test_new_root_runtime_package_requires_classification(tmp_path: Path) -> None:
    package = tmp_path / "new_runtime"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")

    violations = find_root_layout_violations(tmp_path)

    assert violations == [
        "new_runtime: top-level directory is not classified in ALLOWED_ROOT_DIRECTORIES "
        "and looks like a Python runtime package"
    ]


def test_legacy_root_webui_is_reported_as_migration_tail(tmp_path: Path) -> None:
    (tmp_path / "WebUI").mkdir()

    violations = find_root_layout_violations(tmp_path)

    assert violations == ["WebUI: Phase 4 moved WebUI runtime data under Core/data/webui/"]


def test_ownership_table_mentions_migration_tails() -> None:
    table = render_ownership_table()

    assert "`Core/` | Core | application host container" in table
    assert "`logs/` | runtime data | local logs and databases" in table
    assert ALLOWED_ROOT_DIRECTORIES["CoreModules"].owner == "CoreModules"
