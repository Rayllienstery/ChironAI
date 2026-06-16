"""Conditional sys.path setup for editable installs."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def _core_root_from_repo(root: str | Path) -> Path:
    return Path(root).resolve() / "Core"


def ensure_repo_root_on_path(root: str | Path | None = None) -> str:
    """Ensure repository and Core roots are on sys.path; return repository root."""
    resolved = str(Path(root).resolve() if root is not None else _repo_root_from_here())
    core_root = str(_core_root_from_repo(resolved))
    for path in (resolved, core_root):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
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
        ("crawler_service", os.path.join(root, "Core", "modules", "crawler_service")),
        ("html_md", os.path.join(root, "Core", "modules", "html_md")),
        ("error_manager", os.path.join(root, "CoreModules", "ErrorManager")),
        ("rag_service", os.path.join(root, "CoreModules", "RagService")),
        ("md_ingestion_service", os.path.join(root, "CoreModules", "MdIngestionService")),
        ("extensions_backend", os.path.join(root, "Core", "modules", "extensions_backend")),
    )
    for module_name, path in pairs:
        ensure_import_path(module_name, path)


def ensure_webui_composition_paths(project_root: str | Path | None = None) -> str:
    """
    Bootstrap paths for WebUI route composition modules (``webui_routes``, ``llm_proxy_wiring``).

    Uses conditional insertion so editable installs skip redundant ``sys.path`` entries.
    """
    root = ensure_repo_root_on_path(project_root)
    pairs = (
        ("external_docs_rag", os.path.join(root, "Core", "modules", "external_docs_rag")),
        ("webinteraction", os.path.join(root, "CoreModules", "WebInteraction")),
        ("md_ingestion_service", os.path.join(root, "CoreModules", "MdIngestionService")),
        ("rag_service", os.path.join(root, "CoreModules", "RagService")),
        ("llm_proxy", os.path.join(root, "CoreModules", "LlmProxy")),
        ("llm_interactor", os.path.join(root, "CoreModules", "LlmInteractor")),
        ("chironai_security", os.path.join(root, "CoreModules", "Security")),
        ("extensions_sandbox", os.path.join(root, "CoreModules", "ExtensionsSandbox")),
        ("docker_manager", os.path.join(root, "CoreModules", "DockerManager")),
        ("error_manager", os.path.join(root, "CoreModules", "ErrorManager")),
        ("webui_backend", os.path.join(root, "Core", "modules", "webui_backend")),
        ("prompts_manager", os.path.join(root, "Core", "modules", "prompts_manager")),
    )
    for module_name, path in pairs:
        ensure_import_path(module_name, path)
    return root


__all__ = [
    "ensure_import_path",
    "ensure_repo_root_on_path",
    "ensure_webui_composition_paths",
    "ensure_webui_runtime_paths",
]
