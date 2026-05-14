"""Path helpers for the WebUI backend CoreModule."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[3]


def webui_data_dir() -> Path:
    """Return the runtime/data directory used by WebUI backend workflows."""
    configured = (os.getenv("CHIRONAI_WEBUI_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "WebUI"


def coreui_dir() -> Path:
    """Return the CoreUI frontend directory."""
    return project_root() / "CoreModules" / "CoreUI"
