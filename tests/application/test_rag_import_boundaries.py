from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIRS = ("Core/api", "Core/application", "CoreModules", "Core/infrastructure", "Core/modules", "scripts")
REMOVED_RAG_IMPORTS = {
    "application.rag.use_cases",
    "application.container",
    "domain.entities.rag",
    "domain.services.chunking",
    "domain.services.metadata_inference",
    "domain.services.prompt_builder",
    "domain.services.rag_trace",
    "domain.services.rag_trigger",
    "domain.services.rerank",
    "domain.services.retrieval",
}


def _runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for dirname in RUNTIME_DIRS:
        root = REPO_ROOT / dirname
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return files


def _imported_modules(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_runtime_uses_canonical_rag_service_imports() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        source = path.read_text(encoding="utf-8")
        imports = _imported_modules(ast.parse(source, filename=str(path)))
        for removed in REMOVED_RAG_IMPORTS:
            if removed in imports:
                rel_path = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel_path}: {removed}")

    assert offenders == []
