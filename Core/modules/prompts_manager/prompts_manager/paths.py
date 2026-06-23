"""Prompt storage paths owned by prompts_manager."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_MIGRATION_MARKER = ".migrated_from_root"


def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[4]


def webui_data_dir() -> Path:
    """Return the runtime/data directory used by WebUI workflows."""
    configured = (os.getenv("CHIRONAI_WEBUI_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / "WebUI"


def legacy_prompts_dir() -> Path:
    """Former root-level prompts directory (Phase 3 migration source)."""
    return project_root() / "prompts"


def bundled_prompts_dir() -> Path:
    """Shipped default prompt templates bundled with prompts_manager."""
    return Path(__file__).resolve().parent / "bundled"


def runtime_prompts_dir() -> Path:
    """Mutable prompt store for user-created and migrated templates."""
    return webui_data_dir() / "prompts"


def trash_dir() -> Path:
    """Trash folder for deleted prompt templates."""
    return runtime_prompts_dir() / ".trash"


def _copy_tree_files(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if not path.is_file():
            continue
        target = destination / path.name
        if not target.exists():
            shutil.copy2(path, target)


def ensure_prompt_storage_migrated() -> None:
    """Copy legacy root ``prompts/`` content into ``WebUI/prompts/`` once."""
    runtime = runtime_prompts_dir()
    marker = runtime / _MIGRATION_MARKER
    if marker.is_file():
        return

    runtime.mkdir(parents=True, exist_ok=True)
    legacy = legacy_prompts_dir()
    if legacy.is_dir():
        for path in legacy.iterdir():
            if path.name.startswith("."):
                continue
            if path.is_file() and path.suffix.lower() == ".md":
                target = runtime / path.name
                if not target.exists():
                    shutil.copy2(path, target)
            elif path.is_dir() and path.name == ".trash":
                _copy_tree_files(path, trash_dir())

    marker.write_text(f"legacy={legacy}\n", encoding="utf-8")


def resolve_prompts_dir() -> Path:
    """Return the mutable prompt directory, ensuring migration completed."""
    ensure_prompt_storage_migrated()
    runtime_prompts_dir().mkdir(parents=True, exist_ok=True)
    return runtime_prompts_dir()


__all__ = [
    "bundled_prompts_dir",
    "ensure_prompt_storage_migrated",
    "legacy_prompts_dir",
    "project_root",
    "resolve_prompts_dir",
    "runtime_prompts_dir",
    "trash_dir",
    "webui_data_dir",
]
