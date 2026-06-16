"""Port for fetching content from URLs."""

from __future__ import annotations

from typing import Protocol

from external_docs_rag.domain.entities import FetchedDocument


class FetchClient(Protocol):
    """Port for fetching document content from a URL."""

    def fetch(self, url: str, timeout_sec: int = 30, max_size_bytes: int = 2 * 1024 * 1024) -> FetchedDocument | None:
        """
        Fetch content from URL. Returns FetchedDocument or None on failure.
        """
        ...


__all__ = ["FetchClient"]
