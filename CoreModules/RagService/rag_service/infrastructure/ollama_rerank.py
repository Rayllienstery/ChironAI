"""
Ollama rerank client implementing RerankClient.

Calls Ollama via ollama_interactor CLI (subprocess).
"""

from __future__ import annotations

import json
import logging

from rag_service.config import get_ollama_generate_url, get_ollama_rerank_model
from rag_service.domain.services.rerank import (
    extract_candidates_from_rerank_prompt,
    native_rerank_response_to_order,
)
from rag_service.infrastructure.cli_runner import OllamaInteractorCliError, invoke_generate, invoke_rerank

_rerank_log = logging.getLogger("trag.rerank")
_disabled_missing_models: set[str] = set()


def _looks_like_http_404(exc: BaseException) -> bool:
    """True when the failure is almost certainly a missing REST route (common for /api/rerank)."""
    s = str(exc).lower()
    return "404" in s and ("not found" in s or "client error" in s)


def _looks_like_missing_model(exc: BaseException, model: str) -> bool:
    s = str(exc).lower()
    m = (model or "").strip().lower()
    return bool(m and "model" in s and m in s and "not found" in s)


class OllamaRerankClient:
    """Rerank client using Ollama /api/rerank with fallback to /api/generate via CLI."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._url = base_url or get_ollama_generate_url()
        self._model = (model or "").strip() or get_ollama_rerank_model()

    def rerank(self, question: str, prompt_text: str) -> str | None:
        """Return JSON array string (e.g. "[3,1,2]") or None on failure."""
        if not self._model:
            _rerank_log.info("Rerank skipped: no rerank model configured")
            return None
        if self._model in _disabled_missing_models:
            _rerank_log.debug("Rerank skipped: model %r was previously reported missing", self._model)
            return None

        try:
            native_url = self._url.replace("/api/generate", "/api/rerank")
            if native_url == self._url:
                native_url = self._url.rstrip("/") + "/api/rerank"

            candidates = self._extract_candidates_from_prompt(prompt_text)
            if candidates:
                order = self._call_native_rerank(
                    native_url=native_url,
                    question=question,
                    candidates=candidates,
                )
                if order:
                    return json.dumps(order)
        except Exception as e:
            if _looks_like_http_404(e):
                _rerank_log.debug(
                    "Native /api/rerank not available (%s): %s; using generate fallback",
                    type(e).__name__,
                    e,
                )
            else:
                _rerank_log.info("Native /api/rerank failed (%s): %s; falling back", type(e).__name__, e)

        try:
            stdin_obj: dict = {
                "url": self._url,
                "json": {
                    "model": self._model,
                    "prompt": prompt_text,
                    "stream": False,
                    "options": {"num_predict": 256},
                },
                "timeout": 120,
            }
            data = invoke_generate(stdin_obj, default_timeout=120)
            return (data.get("response") or "").strip()
        except OllamaInteractorCliError as e:
            if _looks_like_missing_model(e, self._model):
                _disabled_missing_models.add(self._model)
                _rerank_log.warning(
                    "Rerank disabled for this process: Ollama model %r is not installed. "
                    "Install/pull it or choose an available rerank model; subsequent rerank calls will be skipped.",
                    self._model,
                )
                return None
            if _looks_like_http_404(e):
                _rerank_log.warning(
                    "Rerank generate fallback failed (%s): %s — check OLLAMA_URL / config "
                    "ollama.generate_url (must be Ollama's full …/api/generate URL); "
                    "OpenAI-compatible proxies use different paths.",
                    type(e).__name__,
                    e,
                )
            else:
                _rerank_log.warning("Rerank failed (%s): %s", type(e).__name__, e)
            return None
        except Exception as e:
            _rerank_log.warning("Rerank failed (%s): %s", type(e).__name__, e)
            return None

    def _call_native_rerank(
        self,
        native_url: str,
        question: str,
        candidates: list[tuple[int, str]],
    ) -> list[int] | None:
        """Call /api/rerank and return excerpt indices ordered by relevance."""
        docs: list[str] = [f"IDX{idx}: {txt}" for idx, txt in candidates]
        payload = {
            "model": self._model,
            "query": question,
            "top_n": len(docs),
            "documents": docs,
        }
        stdin_obj: dict = {"url": native_url, "json": payload, "timeout": 120}
        data = invoke_rerank(stdin_obj, default_timeout=120)
        return native_rerank_response_to_order(data)

    @staticmethod
    def _extract_candidates_from_prompt(prompt_text: str) -> list[tuple[int, str]]:
        return extract_candidates_from_rerank_prompt(prompt_text)


__all__ = ["OllamaRerankClient"]
