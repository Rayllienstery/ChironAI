"""
Port for storing and reading RAG trigger keyword collections.

Implementations (e.g. SQLite) live in infrastructure.
Module does not depend on other modules.
"""

from __future__ import annotations

from typing import Any, Protocol


class KeywordCollectionDict(Protocol):
    """Collection as dict: id, name, enabled, keywords."""

    id: str | int
    name: str
    enabled: bool
    keywords: list[str]


class RagKeywordCollectionsRepository(Protocol):
    """Port for keyword collections used to trigger RAG search."""

    def get_all(self) -> list[dict[str, Any]]:
        """
        Return all collections with their keywords.
        Each item: {"id": str|int, "name": str, "enabled": bool, "keywords": list[str]}.
        """
        ...

    def save_collection(
        self,
        collection_id: str | int | None,
        name: str,
        enabled: bool,
        keywords: list[str],
    ) -> str | int:
        """Create or update a collection. Returns the collection id."""
        ...

    def delete_collection(self, collection_id: str | int) -> None:
        """Delete a collection and its keywords."""
        ...

    def get_enabled_keywords_flat(self) -> list[str]:
        """Return a flat list of unique keywords (lowercased) from all enabled collections."""
        ...


__all__ = ["RagKeywordCollectionsRepository", "KeywordCollectionDict"]
