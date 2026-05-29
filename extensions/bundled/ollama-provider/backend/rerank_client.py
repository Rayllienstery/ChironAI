"""
Ollama rerank client for the ollama-provider extension.

Self-contained: helpers from domain.services.rerank are inlined here.
No imports from infrastructure.* or domain.*.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ollama_http import OllamaHttpError, invoke_generate, invoke_rerank as _invoke_rerank

_rerank_log = logging.getLogger("ollama_provider.rerank")
_disabled_missing_models: set[str] = set()


# ---------------------------------------------------------------------------
# Helpers inlined from rag_service.domain.services.rerank
# ---------------------------------------------------------------------------

def _extract_candidates_from_rerank_prompt(prompt_text: str) -> list[tuple[int, str]]:
    """Extract (1-based_index, snippet_text) pairs from a build_rerank_prompt output."""
    text = (prompt_text or "").strip()
    if not text:
        return []
    marker = "Excerpts (each with a number):"
    if marker in text:
        text = text.split(marker, 1)[1]
    if "Reply ONLY" in text:
        text = text.split("Reply ONLY", 1)[0]
    segments = [s.strip() for s in text.split("\n\n") if s.strip()]
    out: list[tuple[int, str]] = []
    for seg in segments:
        m = re.match(r"^\s*(\d+)\s*:\s*(.*)\s*$", seg, flags=re.DOTALL)
        if not m:
            continue
        idx = int(m.group(1))
        snippet = (m.group(2) or "").strip()
        if idx > 0 and snippet:
            out.append((idx, snippet))
    return out


def _native_rerank_response_to_order(raw_response: dict[str, Any]) -> list[int] | None:
    """Convert Ollama native /api/rerank response to a ranked order list."""
    if not raw_response:
        return None
    results = raw_response.get("results") or []
    if not isinstance(results, list):
        return None
    order: list[int] = []
    seen: set[int] = set()
    idx_re = re.compile(r"^\s*IDX(\d+)\s*:", flags=re.IGNORECASE)
    for r in results:
        if not isinstance(r, dict):
            continue
        doc = r.get("document") or ""
        m = idx_re.match(str(doc))
        if not m:
            continue
        idx = int(m.group(1))
        if idx not in seen:
            order.append(idx)
            seen.add(idx)
    return order or None


# ---------------------------------------------------------------------------


def _looks_like_http_404(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "404" in s and ("not found" in s or "client error" in s)


def _looks_like_missing_model(exc: BaseException, model: str) -> bool:
    s = str(exc).lower()
    m = (model or "").strip().lower()
    return bool(m and "model" in s and m in s and "not found" in s)


class OllamaRerankClient:
    """Rerank client using Ollama /api/rerank with fallback to /api/generate."""

    def __init__(self, base_url: str, model: str) -> None:
        self._url = base_url
        self._model = (model or "").strip()

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
            candidates = _extract_candidates_from_rerank_prompt(prompt_text)
            if candidates:
                order = self._call_native_rerank(native_url=native_url, question=question, candidates=candidates)
                if order:
                    return json.dumps(order)
        except Exception as e:
            if _looks_like_http_404(e):
                _rerank_log.debug("Native /api/rerank not available (%s): %s; using generate fallback", type(e).__name__, e)
            else:
                _rerank_log.info("Native /api/rerank failed (%s): %s; falling back", type(e).__name__, e)

        try:
            stdin_obj: dict = {
                "url": self._url,
                "json": {"model": self._model, "prompt": prompt_text, "stream": False, "options": {"num_predict": 256}},
                "timeout": 120,
            }
            data = invoke_generate(stdin_obj, default_timeout=120)
            return (data.get("response") or "").strip()
        except OllamaHttpError as e:
            if _looks_like_missing_model(e, self._model):
                _disabled_missing_models.add(self._model)
                _rerank_log.warning(
                    "Rerank disabled: Ollama model %r is not installed. "
                    "Pull it or choose an available rerank model; subsequent calls will be skipped.",
                    self._model,
                )
                return None
            if _looks_like_http_404(e):
                _rerank_log.warning("Rerank generate fallback failed (%s): %s", type(e).__name__, e)
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
        docs: list[str] = [f"IDX{idx}: {txt}" for idx, txt in candidates]
        payload = {"model": self._model, "query": question, "top_n": len(docs), "documents": docs}
        stdin_obj: dict = {"url": native_url, "json": payload, "timeout": 120}
        data = _invoke_rerank(stdin_obj, default_timeout=120)
        return _native_rerank_response_to_order(data)


__all__ = ["OllamaRerankClient"]
