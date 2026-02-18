"""
Filesystem markdown store implementing MarkdownStore.

Layout: base_dir / source_id / pages / <filename>.md, base_dir / source_id / meta.json.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class FileMarkdownStore:
    """Markdown and metadata store on the filesystem."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = base_dir.rstrip(os.sep)

    def _source_root(self, source_id: str) -> str:
        return os.path.join(self._base_dir, source_id)

    def _pages_dir(self, source_id: str) -> str:
        return os.path.join(self._base_dir, source_id, "pages")

    def _meta_path(self, source_id: str) -> str:
        return os.path.join(self._base_dir, source_id, "meta.json")

    def read_markdown(self, source_id: str, filename: str) -> Optional[str]:
        """Read markdown content. Returns None if not found."""
        path = os.path.join(self._pages_dir(source_id), filename)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def write_markdown(self, source_id: str, filename: str, content: str) -> None:
        """Write markdown content."""
        pages = self._pages_dir(source_id)
        _ensure_dir(pages)
        path = os.path.join(pages, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_meta(self, source_id: str) -> Dict[str, Any]:
        """Read meta.json. Returns {} if not found."""
        path = self._meta_path(source_id)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def write_meta(self, source_id: str, meta: Dict[str, Any]) -> None:
        """Write meta.json."""
        root = self._source_root(source_id)
        _ensure_dir(root)
        path = self._meta_path(source_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def list_filenames(self, source_id: str) -> List[str]:
        """List markdown filenames in pages/ for the source."""
        pages = self._pages_dir(source_id)
        if not os.path.isdir(pages):
            return []
        return [
            f
            for f in os.listdir(pages)
            if f.endswith(".md") and os.path.isfile(os.path.join(pages, f))
        ]


__all__ = ["FileMarkdownStore"]
