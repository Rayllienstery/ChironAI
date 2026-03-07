"""
Normalize markdown content (strip, clean markup).
"""

from __future__ import annotations

from md_ingestion_service.domain.entities import MarkdownFile, NormalizedMarkdown


def normalize(md: MarkdownFile) -> NormalizedMarkdown:
    """Produce normalized markdown from raw. Preserves structure."""
    content = (md.content or "").strip()
    return NormalizedMarkdown(
        source_id=md.source_id,
        filename=md.filename,
        content=content,
        path=md.path or md.filename,
        url=None,
        section_path=None,
    )


__all__ = ["normalize"]
