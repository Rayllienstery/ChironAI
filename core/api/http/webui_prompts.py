"""Prompt/trash filesystem helpers for WebUI routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def is_readme_name(name: str) -> bool:
    """Check if a prompt name is README (case-insensitive)."""
    return (name or "").lower() == "readme"


def has_unsafe_path_segments(name: str) -> bool:
    """Reject path traversal and nested-path prompt identifiers."""
    return ".." in name or "/" in name or "\\" in name


def ensure_prompt_name_is_safe(name: str) -> None:
    """Raise ValueError when the prompt/trash identifier is unsafe."""
    if has_unsafe_path_segments(name):
        raise ValueError("invalid_name")


def prompt_file_path(prompts_dir: Path, name: str) -> Path:
    """Return the markdown file path for a prompt name."""
    return prompts_dir / f"{name}.md"


def prompt_original_name(path_or_name: Path | str) -> str:
    """Extract original prompt name from normal or trash filename."""
    name = path_or_name.stem if isinstance(path_or_name, Path) else Path(path_or_name).stem
    if "." in name:
        parts = name.rsplit(".", 1)
        if parts[1].isdigit():
            return parts[0]
    return name


def prompt_trash_entries(trash_dir: Path) -> list[dict[str, Any]]:
    """Return serialized trash prompt rows sorted by original name."""
    if not trash_dir.is_dir():
        return []
    prompts: list[dict[str, Any]] = []
    for path in trash_dir.iterdir():
        if path.suffix.lower() != ".md" or path.name.startswith("."):
            continue
        prompts.append(
            {
                "name": prompt_original_name(path),
                "trash_name": path.name,
                "trash_path": str(path.relative_to(trash_dir)),
            }
        )
    return sorted(prompts, key=lambda item: str(item["name"]))


def next_trash_prompt_path(trash_dir: Path, name: str) -> Path:
    """Return a unique trash file path for a prompt being moved to trash."""
    trash_path = prompt_file_path(trash_dir, name)
    if trash_path.exists():
        return trash_dir / f"{name}.{int(time.time())}.md"
    return trash_path


__all__ = [
    "ensure_prompt_name_is_safe",
    "has_unsafe_path_segments",
    "is_readme_name",
    "next_trash_prompt_path",
    "prompt_file_path",
    "prompt_original_name",
    "prompt_trash_entries",
]
