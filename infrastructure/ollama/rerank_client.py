"""
Ollama rerank client implementing RerankClient.

Calls Ollama generate API with the rerank prompt; returns raw response string.
"""

from __future__ import annotations

import requests

try:
    from config import get_ollama_generate_url, get_ollama_rerank_model
except ImportError:
    get_ollama_generate_url = lambda: "http://localhost:11434/api/generate"  # type: ignore
    get_ollama_rerank_model = lambda: "devstral-ios"  # type: ignore


class OllamaRerankClient:
    """Rerank LLM client using Ollama /api/generate."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._url = base_url or get_ollama_generate_url()
        self._model = model or get_ollama_rerank_model()

    def rerank(self, question: str, prompt_text: str) -> str | None:
        """Send rerank prompt and return raw response. Returns None on failure."""
        try:
            resp = requests.post(
                self._url,
                json={
                    "model": self._model,
                    "prompt": prompt_text,
                    "stream": False,
                    "options": {"num_predict": 256},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return (resp.json().get("response") or "").strip()
        except Exception:
            return None


__all__ = ["OllamaRerankClient"]
