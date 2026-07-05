"""Report production/test files exceeding line-count policy (Phase 0 / Track A)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PRODUCTION_LIMIT = 800
TEST_LIMIT = 1200

GENERATED_FILE_PATHS = {
    "CoreModules/CoreUI/src/services/api.types.ts",
}

# Paths excluded from enforcement (generated, vendor, build output).
EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "vendor",
    "backups",
    "logs",
    "extensions/bundled",
}

# Documented exceptions: relative path → reason (must stay ≤ limit growth).
DOCUMENTED_EXCEPTIONS: dict[str, str] = {
    "tests/api/test_http_endpoints.py": "Phase 1 split complete; monolith stub retained",
    "tests/api/test_http_chat_completions.py": "Phase 1 domain split; further split deferred",
    "tests/llm_interactor/test_runtime.py": "Interactor runtime characterization suite; split deferred",
    "CoreModules/CoreUI/src/services/api.js": "Phase 3 domain service split complete; facade retained",
    "Core/config/env.py": "Phase 3 acceptable; env overrides cohesive unit",
    "CoreModules/LlmInteractor/llm_interactor/manager.py": "Phase 3 split into manager_* modules; facade retained",
    "CoreModules/CoreUI/src/components/ExtensionsTab.jsx": "Split deferred; RTL smoke pending",
    "CoreModules/CoreUI/src/App.jsx": "App shell; split with router extraction",
    "CoreModules/CoreUI/src/components/TemplateEditorTab.jsx": "Split deferred",
    "CoreModules/CoreUI/src/components/IndexerTester.jsx": "Split deferred",
    "CoreModules/CoreUI/src/components/ModelTester.jsx": "Split deferred",
    "Core/core/openapi.py": "OpenAPI builder; split with codegen track B",
    "CoreModules/RagService/rag_service/domain/services/retrieval.py": "RAG retrieval core; split with domain tests",
    "Core/api/http/webui_dependencies_routes.py": "Dependencies routes; split deferred",
    "Core/api/http/webui_crawler_indexing_runtime_core.py": "Phase 3 crawler split; 804 lines acceptable",
    "CoreModules/LlmProxy/llm_proxy/chat_completions_gemini_native.py": "Gemini path; provider-specific module",
    "CoreModules/LlmProxy/llm_proxy/v1_responses.py": "OpenAI /v1/responses compat layer; vision mapping added in 0.8.9",
}

PRODUCTION_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}


@dataclass(frozen=True)
class Violation:
    path: str
    lines: int
    limit: int
    category: str
    documented: bool


def _is_excluded(path: Path) -> bool:
    rel = path.as_posix()
    if rel.startswith("extensions/bundled/"):
        return True
    if rel in GENERATED_FILE_PATHS:
        return True
    return any(part in EXCLUDE_DIR_NAMES for part in path.parts)


def _is_test_file(rel: str) -> bool:
    normalized = rel.replace("\\", "/")
    if normalized.startswith("tests/"):
        return True
    name = Path(rel).name
    return name.startswith("test_") or name.endswith("_test.py")


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _is_excluded(rel):
            continue
        if path.suffix.lower() not in PRODUCTION_SUFFIXES:
            continue
        if "CoreModules/CoreUI/dist" in str(rel).replace("\\", "/"):
            continue
        files.append(path)
    return sorted(files)


def collect_violations(root: Path = REPO_ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            line_count = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if _is_test_file(rel):
            limit = TEST_LIMIT
            category = "test"
        else:
            limit = PRODUCTION_LIMIT
            category = "production"
        if line_count <= limit:
            continue
        documented = rel in DOCUMENTED_EXCEPTIONS
        violations.append(
            Violation(path=rel, lines=line_count, limit=limit, category=category, documented=documented)
        )
    return sorted(violations, key=lambda v: (-v.lines, v.path))


def format_report(violations: list[Violation]) -> str:
    lines = [
        "# Oversized file audit",
        f"Production limit: {PRODUCTION_LIMIT} lines",
        f"Test limit: {TEST_LIMIT} lines",
        "",
    ]
    if not violations:
        lines.append("No violations.")
        return "\n".join(lines) + "\n"

    undocumented = [v for v in violations if not v.documented]
    documented = [v for v in violations if v.documented]
    lines.append(f"Total over limit: {len(violations)} ({len(undocumented)} undocumented)")
    lines.append("")
    if undocumented:
        lines.append("## Undocumented (fail gate)")
        for v in undocumented:
            lines.append(f"- {v.path}: {v.lines} lines ({v.category}, limit {v.limit})")
        lines.append("")
    if documented:
        lines.append("## Documented exceptions (advisory)")
        for v in documented:
            reason = DOCUMENTED_EXCEPTIONS.get(v.path, "")
            lines.append(f"- {v.path}: {v.lines} lines — {reason}")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit files exceeding line-count policy.")
    parser.add_argument(
        "--mode",
        choices=("report", "check"),
        default="report",
        help="report: print summary; check: exit 1 on new undocumented violations",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the report (used with --mode report).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    violations = collect_violations()
    report = format_report(violations)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")
    if args.mode == "check":
        undocumented = [v for v in violations if not v.documented]
        if undocumented:
            print(f"FAIL: {len(undocumented)} undocumented oversized file(s).", file=sys.stderr)
            return 1
        print("PASS: no new undocumented oversized files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
