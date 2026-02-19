"""
Markdown store port.

Abstract interface for reading/writing markdown files and metadata (e.g. meta.json).
Implementations (filesystem) live in infrastructure.
"""

from __future__ import annotations

from typing import Any, Protocol


class MarkdownStore(Protocol):
    """Port for persisting and reading markdown and per-source metadata."""

    def read_markdown(self, source_id: str, filename: str) -> str | None:
        """Read markdown content for a file. Returns None if not found."""
        ...

    def write_markdown(self, source_id: str, filename: str, content: str) -> None:
        """Write markdown content for a file."""
        ...

    def read_meta(self, source_id: str) -> dict[str, Any]:
        """Read metadata (e.g. meta.json) for a source. Returns {} if not found."""
        ...

    def write_meta(self, source_id: str, meta: dict[str, Any]) -> None:
        """Write metadata for a source."""
        ...

    def list_filenames(self, source_id: str) -> list[str]:
        """List markdown filenames for a source."""
        ...


__all__ = ["MarkdownStore"]
