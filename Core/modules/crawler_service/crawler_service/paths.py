"""Resolve WebUI directory and project root for crawl I/O."""

from __future__ import annotations

import os
from pathlib import Path

from core.webui_data_paths import resolve_webui_data_dir


def default_project_root() -> Path:
    """Infer repo root from CHIRONAI_PROJECT_ROOT or cwd."""
    env = os.environ.get("CHIRONAI_PROJECT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def resolve_webui_dir(project_root: Path | None = None) -> Path:
    """WebUI runtime/data directory (contains rag_sources)."""
    root = project_root or default_project_root()
    return resolve_webui_data_dir(root)


def rag_sources_dir(webui_dir: Path) -> Path:
    return webui_dir / "rag_sources"
