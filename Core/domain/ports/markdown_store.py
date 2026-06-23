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
        """Read markdown content for a file.

        Args:
            source_id: The crawl source identifier (e.g. ``apple_docs``).
            filename: The markdown file name (e.g. ``swift-arrays.md``).

        Returns:
            The file contents as a string, or ``None`` if the file does not exist.
        """
        ...

    def write_markdown(self, source_id: str, filename: str, content: str) -> None:
        """Write markdown content for a file.

        Args:
            source_id: The crawl source identifier.
            filename: The markdown file name.
            content: The full markdown content to persist.
        """
        ...

    def read_meta(self, source_id: str) -> dict[str, Any]:
        """Read metadata (e.g. ``meta.json``) for a source.

        Args:
            source_id: The crawl source identifier.

        Returns:
            The metadata dictionary, or ``{}`` if no metadata exists yet.
        """
        ...

    def write_meta(self, source_id: str, meta: dict[str, Any]) -> None:
        """Write metadata for a source.

        Args:
            source_id: The crawl source identifier.
            meta: The metadata payload to persist.
        """
        ...

    def list_filenames(self, source_id: str) -> list[str]:
        """List markdown filenames for a source.

        Args:
            source_id: The crawl source identifier.

        Returns:
            A list of markdown file names (no directory prefixes).
        """
        ...


__all__ = ["MarkdownStore"]
