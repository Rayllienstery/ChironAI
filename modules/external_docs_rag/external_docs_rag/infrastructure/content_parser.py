"""
Content parser: HTML → Markdown and raw text normalization.
"""

from __future__ import annotations

import re

from external_docs_rag.domain.entities import FetchedDocument
from external_docs_rag.infrastructure.http_fetch import normalize_raw_markdown

try:
    import html2text
    _HAS_HTML2TEXT = True
except ImportError:
    _HAS_HTML2TEXT = False
    html2text = None  # type: ignore


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using html2text if available, else regex fallback."""
    if not html or not html.strip():
        return ""
    if _HAS_HTML2TEXT and html2text is not None:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        try:
            return re.sub(r"\n{3,}", "\n\n", h.handle(html).strip())
        except Exception:
            pass
    return _html_to_markdown_regex(html)


def _html_to_markdown_regex(html: str) -> str:
    """Fallback: strip tags and normalize whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def parse_document_to_markdown(doc: FetchedDocument) -> str:
    """
    Convert a fetched document to normalized markdown.
    Raw markdown/plain: normalize newlines. HTML: convert to markdown.
    """
    if not doc or not doc.content:
        return ""
    ct = (doc.content_type or "").lower()
    if "html" in ct:
        return html_to_markdown(doc.content)
    return normalize_raw_markdown(doc.content)


__all__ = ["html_to_markdown", "parse_document_to_markdown"]
