"""
Filesystem source store: list and read markdown files from a directory.
"""

from __future__ import annotations

import os

from md_ingestion_service.domain.entities import MarkdownFile
from md_ingestion_service.domain.ports import SourceStore


class FsSourceStore:
    """Read markdown files from a local directory."""

    def list_files(self, source_id: str, base_path: str) -> list[str]:
        if not base_path or not os.path.isdir(base_path):
            return []
        out = []
        for root, _dirs, files in os.walk(base_path):
            for f in files:
                if f.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, f), base_path)
                    out.append(rel.replace("\\", "/"))
        return sorted(out)

    def read_file(self, source_id: str, base_path: str, relative_path: str) -> MarkdownFile | None:
        path = os.path.join(base_path, relative_path)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
        except OSError:
            return None
        return MarkdownFile(
            source_id=source_id,
            filename=os.path.basename(path),
            content=content,
            path=relative_path.replace("\\", "/"),
        )


__all__ = ["FsSourceStore"]
