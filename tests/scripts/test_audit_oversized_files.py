from __future__ import annotations

from pathlib import Path

from scripts import audit_oversized_files


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * count, encoding="utf-8")


def test_generated_api_types_are_excluded_from_line_count(tmp_path: Path) -> None:
    generated = tmp_path / "CoreModules" / "CoreUI" / "src" / "services" / "api.types.ts"
    _write_lines(generated, audit_oversized_files.PRODUCTION_LIMIT + 100)

    violations = audit_oversized_files.collect_violations(tmp_path)

    assert violations == []


def test_undocumented_oversized_file_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "Core" / "example.py"
    _write_lines(source, audit_oversized_files.PRODUCTION_LIMIT + 1)

    violations = audit_oversized_files.collect_violations(tmp_path)

    assert violations == [
        audit_oversized_files.Violation(
            path="Core/example.py",
            lines=audit_oversized_files.PRODUCTION_LIMIT + 1,
            limit=audit_oversized_files.PRODUCTION_LIMIT,
            category="production",
            documented=False,
        )
    ]
