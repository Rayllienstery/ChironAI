"""Conditional sys.path setup for editable installs (Phase 4 / Track E)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_repo_root_on_path(root: str | Path | None = None) -> str:
    """Ensure repository root is on sys.path; return normalized root string."""
    resolved = str(Path(root).resolve() if root is not None else _repo_root_from_here())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
    return resolved


def ensure_import_path(module_name: str, path: str | Path) -> None:
    """
    Add ``path`` to sys.path only when ``module_name`` is not already importable.

    Skips insertion when the package is provided by ``pip install -e``.
    """
    if importlib.util.find_spec(module_name) is not None:
        return
    normalized = str(Path(path).resolve())
    if os.path.isdir(normalized) and normalized not in sys.path:
        sys.path.insert(0, normalized)


def ensure_webui_runtime_paths(project_root: str | Path) -> None:
    """Bootstrap paths for the WebUI backend entrypoint when not installed editable."""
    root = ensure_repo_root_on_path(project_root)
    pairs = (
        ("crawler_service", os.path.join(root, "modules", "crawler_service")),
        ("html_md", os.path.join(root, "modules", "html_md")),
        ("error_manager", os.path.join(root, "CoreModules", "ErrorManager")),
        ("rag_service", os.path.join(root, "CoreModules", "RagService")),
        ("md_ingestion_service", os.path.join(root, "CoreModules", "MdIngestionService")),
        ("extensions_backend", os.path.join(root, "modules", "extensions_backend")),
    )
    for module_name, path in pairs:
        ensure_import_path(module_name, path)


__all__ = ["ensure_import_path", "ensure_repo_root_on_path", "ensure_webui_runtime_paths"]
