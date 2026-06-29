"""Path helpers for the canonical WebUI backend module."""

from __future__ import annotations

from pathlib import Path

from core.webui_data_paths import resolve_webui_data_dir


def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[4]


def webui_data_dir() -> Path:
    """Return the runtime/data directory used by WebUI backend workflows."""
    return resolve_webui_data_dir(project_root())


def coreui_dir() -> Path:
    """Return the CoreUI frontend directory."""
    return project_root() / "CoreModules" / "CoreUI"
