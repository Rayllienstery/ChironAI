"""Provider-runtime backed RAG adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from llm_interactor.contracts import LLMRequest

from rag_service.domain.errors import EmbeddingError
from rag_service.domain.services.retrieval import MAX_EMBED_TEXT_LENGTH

_rerank_log = logging.getLogger("trag.rerank")


class RuntimeBackedEmbeddingProvider:
    """EmbeddingProvider bridge over LLMRuntime with legacy fallback support."""

    def __init__(
        self,
        *,
        runtime_getter: Callable[[], Any | None] | None = None,
        runtime: Any | None = None,
        provider_id: str = "ollama",
        model: str | None = None,
        delegate: Any | None = None,
    ) -> None:
        self._runtime_getter = runtime_getter
        self._runtime = runtime
        self._provider_id = provider_id
        self._delegate = delegate
        self._model = (model or getattr(delegate, "_model", None) or getattr(delegate, "model", None) or "").strip()
        self.model = self._model

    def _resolved_runtime(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        if self._runtime_getter is None:
            return None
        return self._runtime_getter()

    def _sync_delegate_model(self) -> None:
        if self._delegate is None:
            return
        if hasattr(self._delegate, "_model"):
            setattr(self._delegate, "_model", self._model)
        elif hasattr(self._delegate, "model"):
            setattr(self._delegate, "model", self._model)

    def embed(self, text: str) -> list[float]:
        current_model = (self._model or self.model or "").strip()
        self._model = current_model
        self.model = current_model
        runtime = self._resolved_runtime()
        if runtime is None:
            if self._delegate is None:
                raise EmbeddingError("LLM runtime is unavailable for embeddings")
            self._sync_delegate_model()
            return self._delegate.embed(text)
        truncated = text[:MAX_EMBED_TEXT_LENGTH] if len(text) > MAX_EMBED_TEXT_LENGTH else text
        try:
            response = runtime.invoke(
                LLMRequest(
                    provider_id=self._provider_id,
                    model=current_model,
                    operation="embed",
                    input_text=truncated,
                )
            )
            raw = response.raw or {}
            embedding = raw.get("embedding")
            if embedding is None:
                embeddings = raw.get("embeddings")
                if isinstance(embeddings, list) and embeddings:
                    embedding = embeddings[0]
            if not isinstance(embedding, list):
                raise EmbeddingError(f"No embedding in provider response: {raw}")
            return [float(v) for v in embedding]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Provider embed error (model={current_model}): {exc}") from exc

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        current_model = (self._model or self.model or "").strip()
        self._model = current_model
        self.model = current_model
        runtime = self._resolved_runtime()
        if runtime is None:
            if self._delegate is None:
                raise EmbeddingError("LLM runtime is unavailable for batch embeddings")
            self._sync_delegate_model()
            return self._delegate.embed_batch(texts)
        truncated = [text[:MAX_EMBED_TEXT_LENGTH] if len(text) > MAX_EMBED_TEXT_LENGTH else text for text in texts]
        try:
            response = runtime.invoke(
                LLMRequest(
                    provider_id=self._provider_id,
                    model=current_model,
                    operation="embed",
                    input_texts=truncated,
                )
            )
            raw = response.raw or {}
            embeddings = raw.get("embeddings")
            if not isinstance(embeddings, list):
                raise EmbeddingError(f"No embeddings in provider response: {raw}")
            if len(embeddings) != len(truncated):
                raise EmbeddingError(
                    f"Provider returned {len(embeddings)} embeddings for {len(truncated)} inputs"
                )
            return [[float(v) for v in embedding] for embedding in embeddings]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Provider embed batch error (model={current_model}): {exc}") from exc


class RuntimeBackedRerankClient:
    """RerankClient bridge over LLMRuntime with legacy fallback support."""

    def __init__(
        self,
        *,
        runtime_getter: Callable[[], Any | None] | None = None,
        runtime: Any | None = None,
        provider_id: str = "ollama",
        model: str | None = None,
        delegate: Any | None = None,
    ) -> None:
        self._runtime_getter = runtime_getter
        self._runtime = runtime
        self._provider_id = provider_id
        self._delegate = delegate
        self._model = (model or getattr(delegate, "_model", None) or getattr(delegate, "model", None) or "").strip()
        self.model = self._model

    def _resolved_runtime(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        if self._runtime_getter is None:
            return None
        return self._runtime_getter()

    def _sync_delegate_model(self) -> None:
        if self._delegate is None:
            return
        if hasattr(self._delegate, "_model"):
            setattr(self._delegate, "_model", self._model)
        elif hasattr(self._delegate, "model"):
            setattr(self._delegate, "model", self._model)

    def rerank(self, question: str, prompt_text: str) -> str | None:
        current_model = (self._model or self.model or "").strip()
        self._model = current_model
        self.model = current_model
        if not current_model:
            _rerank_log.info("Rerank skipped: no rerank model configured")
            return None
        runtime = self._resolved_runtime()
        if runtime is None:
            if self._delegate is None:
                return None
            self._sync_delegate_model()
            return self._delegate.rerank(question, prompt_text)
        try:
            response = runtime.invoke(
                LLMRequest(
                    provider_id=self._provider_id,
                    model=current_model,
                    operation="rerank",
                    rerank_query=question,
                    rerank_prompt=prompt_text,
                )
            )
            raw = response.raw or {}
            return str(response.text or raw.get("response") or "").strip() or None
        except Exception as exc:
            _rerank_log.warning("Provider rerank failed (%s): %s", type(exc).__name__, exc)
            if self._delegate is None:
                return None
            self._sync_delegate_model()
            return self._delegate.rerank(question, prompt_text)


__all__ = ["RuntimeBackedEmbeddingProvider", "RuntimeBackedRerankClient"]
