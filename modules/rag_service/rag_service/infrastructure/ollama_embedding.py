"""
Ollama embedding client implementing EmbeddingProvider.
"""

from __future__ import annotations

import requests

from rag_service.domain.errors import EmbeddingError
from rag_service.domain.services.retrieval import MAX_EMBED_TEXT_LENGTH

try:
    from config import get_ollama_embed_model, get_ollama_embed_url
except ImportError:
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore
    get_ollama_embed_model = lambda: "mxbai-embed-large"  # type: ignore


class OllamaEmbeddingProvider:
    """Embedding provider using Ollama /api/embed."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._url = base_url or get_ollama_embed_url()
        self._model = model or get_ollama_embed_model()

    def embed(self, text: str) -> list[float]:
        if len(text) > MAX_EMBED_TEXT_LENGTH:
            text = text[:MAX_EMBED_TEXT_LENGTH]
        try:
            resp = requests.post(
                self._url,
                json={"model": self._model, "input": text},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings")
            if not embeddings:
                raise EmbeddingError(f"No 'embeddings' key in Ollama response: {data}")
            if isinstance(embeddings, list) and len(embeddings) > 0:
                first = embeddings[0]
                return first if isinstance(first, list) else list(first)
            raise EmbeddingError(f"Unexpected embeddings format: {embeddings}")
        except requests.exceptions.RequestException as e:
            raise EmbeddingError(f"Ollama embed API error (model={self._model}): {e}") from e
        except (ValueError, TypeError) as e:
            raise EmbeddingError(str(e)) from e

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        truncated = [t[:MAX_EMBED_TEXT_LENGTH] if len(t) > MAX_EMBED_TEXT_LENGTH else t for t in texts]
        try:
            resp = requests.post(
                self._url,
                json={"model": self._model, "input": truncated},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings")
            if embeddings is None:
                raise EmbeddingError("No 'embeddings' key in Ollama response")
            if len(embeddings) != len(truncated):
                raise EmbeddingError(f"Ollama returned {len(embeddings)} embeddings for {len(truncated)} inputs")
            return [e if isinstance(e, list) else list(e) for e in embeddings]
        except requests.exceptions.RequestException as e:
            raise EmbeddingError(f"Ollama embed batch API error: {e}") from e
        except (ValueError, TypeError) as e:
            raise EmbeddingError(str(e)) from e


__all__ = ["OllamaEmbeddingProvider"]
