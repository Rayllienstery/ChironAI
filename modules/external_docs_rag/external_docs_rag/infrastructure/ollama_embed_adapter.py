"""
Ollama embedding adapter implementing EmbeddingPort for use in ingest CLI.
Uses env OLLAMA_EMBED_URL and RAG_EMBED_MODEL (or OLLAMA_EMBED_MODEL).
"""

from __future__ import annotations

import os

try:
    import requests
except ImportError:
    requests = None  # type: ignore

DEFAULT_EMBED_URL = "http://localhost:11434/api/embed"
DEFAULT_EMBED_MODEL = "mxbai-embed-large"
MAX_EMBED_TEXT_LENGTH = 8192


class OllamaEmbedAdapter:
    """EmbeddingPort implementation via Ollama /api/embed."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._url = (base_url or os.getenv("OLLAMA_EMBED_URL", DEFAULT_EMBED_URL)).rstrip("/")
        self._model = model or os.getenv("RAG_EMBED_MODEL") or os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    def embed(self, text: str) -> list[float]:
        if not requests:
            raise RuntimeError("requests required for OllamaEmbedAdapter")
        t = text[:MAX_EMBED_TEXT_LENGTH] if len(text) > MAX_EMBED_TEXT_LENGTH else text
        resp = requests.post(self._url, json={"model": self._model, "input": t}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embeddings")
        if emb and isinstance(emb, list) and len(emb) > 0:
            v = emb[0]
            return list(v) if isinstance(v, (list, tuple)) else []
        raise RuntimeError(f"No embeddings in response: {data}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not requests:
            raise RuntimeError("requests required for OllamaEmbedAdapter")
        truncated = [t[:MAX_EMBED_TEXT_LENGTH] if len(t) > MAX_EMBED_TEXT_LENGTH else t for t in texts]
        resp = requests.post(self._url, json={"model": self._model, "input": truncated}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embeddings") or []
        if len(emb) != len(texts):
            raise RuntimeError(f"Ollama returned {len(emb)} embeddings for {len(texts)} texts")
        return [list(v) if isinstance(v, (list, tuple)) else [] for v in emb]


__all__ = ["OllamaEmbedAdapter"]
