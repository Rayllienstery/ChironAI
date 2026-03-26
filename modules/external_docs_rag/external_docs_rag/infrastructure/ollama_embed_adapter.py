"""
Ollama embedding adapter implementing EmbeddingPort for use in ingest CLI.

Uses OllamaInteractor subprocess (invoke_embed); env OLLAMA_EMBED_URL and RAG_EMBED_MODEL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root: .../modules/external_docs_rag/external_docs_rag/infrastructure -> parents[4] == project root
_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from infrastructure.ollama.cli_runner import OllamaInteractorCliError, invoke_embed

DEFAULT_EMBED_URL = "http://localhost:11434/api/embed"
DEFAULT_EMBED_MODEL = "mxbai-embed-large"
MAX_EMBED_TEXT_LENGTH = 8192


class OllamaEmbedAdapter:
    """EmbeddingPort implementation via Ollama /api/embed (CLI)."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._url = (base_url or os.getenv("OLLAMA_EMBED_URL", DEFAULT_EMBED_URL)).rstrip("/")
        self._model = model or os.getenv("RAG_EMBED_MODEL") or os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    def embed(self, text: str) -> list[float]:
        t = text[:MAX_EMBED_TEXT_LENGTH] if len(text) > MAX_EMBED_TEXT_LENGTH else text
        try:
            data = invoke_embed(
                {"url": self._url, "json": {"model": self._model, "input": t}, "timeout": 60},
                default_timeout=60,
            )
        except OllamaInteractorCliError as e:
            raise RuntimeError(str(e)) from e
        emb = data.get("embeddings")
        if emb and isinstance(emb, list) and len(emb) > 0:
            v = emb[0]
            return list(v) if isinstance(v, (list, tuple)) else []
        raise RuntimeError(f"No embeddings in response: {data}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        truncated = [t[:MAX_EMBED_TEXT_LENGTH] if len(t) > MAX_EMBED_TEXT_LENGTH else t for t in texts]
        try:
            data = invoke_embed(
                {"url": self._url, "json": {"model": self._model, "input": truncated}, "timeout": 120},
                default_timeout=120,
            )
        except OllamaInteractorCliError as e:
            raise RuntimeError(str(e)) from e
        emb = data.get("embeddings") or []
        if len(emb) != len(texts):
            raise RuntimeError(f"Ollama returned {len(emb)} embeddings for {len(texts)} texts")
        return [list(v) if isinstance(v, (list, tuple)) else [] for v in emb]


__all__ = ["OllamaEmbedAdapter"]
