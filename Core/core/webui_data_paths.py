"""Canonical WebUI runtime data directory resolution."""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

_LEGACY_DIR_NAME = "WebUI"
_DATA_REL = Path("Core") / "data" / "webui"
_DIR_MIGRATION_MARKER = ".migrated_from_root_webui"


def default_webui_data_dir(repo_root: Path) -> Path:
    """Default host-owned WebUI runtime data directory."""
    return repo_root / _DATA_REL


def legacy_webui_data_dir(repo_root: Path) -> Path:
    """Former root-level WebUI runtime data directory."""
    return repo_root / _LEGACY_DIR_NAME


def resolve_webui_data_dir(repo_root: Path) -> Path:
    """Resolve WebUI runtime data dir, migrating legacy root ``WebUI/`` once."""
    configured = (os.getenv("CHIRONAI_WEBUI_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    target = default_webui_data_dir(repo_root)
    legacy = legacy_webui_data_dir(repo_root)
    marker = target / _DIR_MIGRATION_MARKER
    if not marker.is_file() and legacy.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = target / item.name
            if dest.exists():
                continue
            shutil.move(str(item), str(dest))
        marker.write_text(f"legacy={legacy}\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            legacy.rmdir()
    return target


__all__ = [
    "default_webui_data_dir",
    "legacy_webui_data_dir",
    "resolve_webui_data_dir",
]
