"""
Embedding provider port.

Abstract interface for generating text embeddings.
Implementations (e.g. Ollama /api/embed) live in infrastructure.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Port for generating embeddings from text."""

    def embed(self, text: str) -> list[float]:
        """Embed a single text. Raises domain.errors.EmbeddingError on failure."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Raises domain.errors.EmbeddingError on failure."""
        ...


__all__ = ["EmbeddingProvider"]
