"""
Filesystem infrastructure.

Adapters for persisting markdown pages, meta.json, and other on-disk
artifacts required by crawling and indexing flows.
"""

from infrastructure.fs.markdown_store import FileMarkdownStore

__all__ = ["FileMarkdownStore"]
