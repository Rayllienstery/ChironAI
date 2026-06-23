"""
Ollama embedding client for the ollama-provider extension.

Self-contained: no imports from infrastructure.* or domain.*.
"""

from __future__ import annotations

from ollama_http import OllamaHttpError, invoke_embed

# Safety truncation limit for embedding inputs (characters).
_MAX_EMBED_TEXT_LENGTH = 32_000


class OllamaEmbeddingProvider:
    """Embedding provider using Ollama /api/embed via ollama_interactor CLI."""

    def __init__(
        self,
        base_url: str,
        model: str,
        embed_timeout_seconds: float = 180.0,
    ) -> None:
        self._url = base_url
        self._model = model
        self._embed_timeout = float(embed_timeout_seconds)

    def embed(self, text: str) -> list[float]:
        """Embed a single text. Raises RuntimeError on failure."""
        if len(text) > _MAX_EMBED_TEXT_LENGTH:
            text = text[:_MAX_EMBED_TEXT_LENGTH]
        t = max(10.0, self._embed_timeout)
        stdin_obj: dict = {"url": self._url, "json": {"model": self._model, "input": text}, "timeout": t}
        try:
            data = invoke_embed(stdin_obj, default_timeout=t)
            embeddings = data.get("embeddings")
            if not embeddings:
                raise RuntimeError(f"No 'embeddings' key in Ollama response: {data}")
            if isinstance(embeddings, list) and len(embeddings) > 0:
                first = embeddings[0]
                return first if isinstance(first, list) else list(first)
            raise RuntimeError(f"Unexpected embeddings format: {embeddings}")
        except OllamaHttpError as e:
            raise RuntimeError(f"Ollama embed API error (model={self._model}, url={self._url}): {e}") from e

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Raises RuntimeError on failure."""
        if not texts:
            return []
        truncated = [t[:_MAX_EMBED_TEXT_LENGTH] if len(t) > _MAX_EMBED_TEXT_LENGTH else t for t in texts]
        batch_t = max(120.0, self._embed_timeout * 2.0)
        stdin_obj: dict = {"url": self._url, "json": {"model": self._model, "input": truncated}, "timeout": batch_t}
        try:
            data = invoke_embed(stdin_obj, default_timeout=batch_t)
            embeddings = data.get("embeddings")
            if embeddings is None:
                raise RuntimeError("No 'embeddings' key in Ollama response")
            if len(embeddings) != len(truncated):
                raise RuntimeError(f"Ollama returned {len(embeddings)} embeddings for {len(truncated)} inputs")
            return [e if isinstance(e, list) else list(e) for e in embeddings]
        except OllamaHttpError as e:
            raise RuntimeError(f"Ollama embed batch API error (model={self._model}): {e}") from e


__all__ = ["OllamaEmbeddingProvider"]
