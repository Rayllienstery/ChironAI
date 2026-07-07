"""Path helpers for the canonical WebUI backend module."""

from __future__ import annotations

import os
from pathlib import Path

from core.webui_data_paths import resolve_webui_data_dir


def project_root() -> Path:
    """Return the repository root (works from source or wheel installs)."""
    override = (os.getenv("CHIRONAI_REPO_ROOT") or os.getenv("REPO_ROOT") or "").strip()
    if override:
        return Path(override).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "Core").is_dir():
            return candidate

    return Path(__file__).resolve().parents[4]


def webui_data_dir() -> Path:
    """Return the runtime/data directory used by WebUI backend workflows."""
    return resolve_webui_data_dir(project_root())


def coreui_dir() -> Path:
    """Return the CoreUI frontend directory."""
    return project_root() / "CoreModules" / "CoreUI"
