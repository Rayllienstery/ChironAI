"""Port for computing embeddings."""

from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    """Port for embedding text to vectors."""

    def embed(self, text: str) -> list[float]:
        """Embed a single text. Returns vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns list of vectors."""
        ...


__all__ = ["EmbeddingPort"]
