"""
Source store port: read markdown and list files from a source (FS, Git, etc.).
"""

from __future__ import annotations

from typing import Protocol

from md_ingestion_service.domain.entities import MarkdownFile


class SourceStore(Protocol):
    """Port for reading raw markdown from a source."""

    def list_files(self, source_id: str, base_path: str) -> list[str]:
        """List relative paths of markdown files under base_path."""
        ...

    def read_file(self, source_id: str, base_path: str, relative_path: str) -> MarkdownFile | None:
        """Read a single file as MarkdownFile. None if not found."""
        ...


__all__ = ["SourceStore"]
