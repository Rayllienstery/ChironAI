"""Workspace root injection (repository root for file tools and apply-edit)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

_workspace_root_fn: Callable[[], Path] | None = None


def set_workspace_root(fn: Callable[[], Path]) -> None:
    global _workspace_root_fn
    _workspace_root_fn = fn


def workspace_root() -> Path:
    if _workspace_root_fn is None:
        raise RuntimeError("workspace root not configured; call set_workspace_root from host wiring")
    return _workspace_root_fn()
