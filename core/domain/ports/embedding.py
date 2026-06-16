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
        """Embed a single text.

        Args:
            text: The text to generate an embedding for.

        Returns:
            A list of floats representing the dense vector embedding.

        Raises:
            domain.errors.EmbeddingError: If the embedding generation fails.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch.

        Args:
            texts: A list of strings to generate embeddings for.

        Returns:
            A list of lists of floats, where each inner list is a dense vector.

        Raises:
            domain.errors.EmbeddingError: If the batch embedding generation fails.
        """
        ...


__all__ = ["EmbeddingProvider"]
