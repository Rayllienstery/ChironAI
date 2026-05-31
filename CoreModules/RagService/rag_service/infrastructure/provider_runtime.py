"""Provider-runtime backed RAG adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from llm_interactor.contracts import LLMRequest

from rag_service.domain.errors import EmbeddingError
from rag_service.domain.services.retrieval import MAX_EMBED_TEXT_LENGTH

_rerank_log = logging.getLogger("trag.rerank")
def _runtime_unavailable_message() -> str:
    return (
        "LLM provider runtime is unavailable. Enable the ollama-provider extension, "
        "wait for extension bootstrap to finish (Extensions tab), and retry. "
        "If Docker shows a running Ollama container under another name, set OLLAMA_CONTAINER_NAME."
    )


_RUNTIME_UNAVAILABLE = _runtime_unavailable_message()


def _require_runtime(runtime_getter: Callable[[], Any | None] | None, runtime: Any | None) -> Any:
    if runtime is not None:
        return runtime
    if runtime_getter is not None:
        resolved = runtime_getter()
        if resolved is not None:
            return resolved
    try:
        from flask import has_app_context, current_app

        if has_app_context():
            app = current_app._get_current_object()
            wiring = getattr(app, "extensions", {}).get("llm_proxy_wiring")
            manager = getattr(wiring, "extension_manager", None) if wiring is not None else None
            wired_runtime = getattr(wiring, "llm_runtime", None) if wiring is not None else None
            if wired_runtime is not None:
                return wired_runtime
            if manager is not None:
                from api.http.llm_runtime_access import resolve_llm_runtime

                resolved = resolve_llm_runtime(extension_manager=manager, sync_bootstrap=True)
                if resolved is not None:
                    return resolved
            from api.http.llm_runtime_access import ensure_llm_runtime_for_app

            resolved = ensure_llm_runtime_for_app(app)
            if resolved is not None:
                return resolved
    except Exception:
        pass
    detail = ""
    try:
        from flask import has_app_context, current_app

        if has_app_context():
            from api.http.extensions_service_access import get_extensions_service

            svc = get_extensions_service(current_app._get_current_object())
            if svc is not None:
                status = str(getattr(svc, "runtime_status", "") or "")
                err = str(getattr(svc, "runtime_error", "") or "").strip()
                if status or err:
                    detail = f" (extensions status={status}" + (f", error={err}" if err else "") + ")"
    except Exception:
        pass
    raise EmbeddingError(_RUNTIME_UNAVAILABLE + detail)


class RuntimeBackedEmbeddingProvider:
    """EmbeddingProvider bridge over LLMRuntime."""

    def __init__(
        self,
        *,
        runtime_getter: Callable[[], Any | None] | None = None,
        runtime: Any | None = None,
        provider_id: str = "ollama",
        model: str | None = None,
    ) -> None:
        self._runtime_getter = runtime_getter
        self._runtime = runtime
        self._provider_id = provider_id
        self._model = (model or "").strip()
        self.model = self._model

    def _resolved_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        return _require_runtime(self._runtime_getter, None)

    def embed(self, text: str) -> list[float]:
        current_model = (self._model or self.model or "").strip()
        self._model = current_model
        self.model = current_model
        runtime = self._resolved_runtime()
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
    """RerankClient bridge over LLMRuntime."""

    def __init__(
        self,
        *,
        runtime_getter: Callable[[], Any | None] | None = None,
        runtime: Any | None = None,
        provider_id: str = "ollama",
        model: str | None = None,
    ) -> None:
        self._runtime_getter = runtime_getter
        self._runtime = runtime
        self._provider_id = provider_id
        self._model = (model or "").strip()
        self.model = self._model

    def _resolved_runtime(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        if self._runtime_getter is None:
            return None
        try:
            return self._runtime_getter()
        except Exception:
            return None

    def rerank(self, question: str, prompt_text: str) -> str | None:
        current_model = (self._model or self.model or "").strip()
        self._model = current_model
        self.model = current_model
        if not current_model:
            _rerank_log.info("Rerank skipped: no rerank model configured")
            return None
        runtime = self._resolved_runtime()
        if runtime is None:
            _rerank_log.warning("Rerank skipped: LLM runtime unavailable")
            return None
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
            return None


class RuntimeResolvingChatClient:
    """Lazy chat client that resolves RuntimeBackedChatClient when the runtime is ready."""

    def __init__(
        self,
        *,
        runtime_getter: Callable[[], Any | None] | None = None,
        runtime: Any | None = None,
        provider_id: str = "ollama",
        model: str | None = None,
        fallback: Any | None = None,
    ) -> None:
        self._runtime = runtime
        self._runtime_getter = runtime_getter
        self._provider_id = provider_id
        self._model = (model or "").strip()
        self._fallback = fallback

    def _resolved_runtime(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        if self._runtime_getter is None:
            return None
        try:
            resolved = self._runtime_getter()
            if resolved is not None:
                self._runtime = resolved
            return resolved
        except Exception:
            return None

    def _delegate(self) -> Any:
        runtime = self._resolved_runtime()
        if runtime is not None:
            from llm_interactor import RuntimeBackedChatClient  # noqa: PLC0415

            return RuntimeBackedChatClient(runtime, provider_id=self._provider_id)
        if self._fallback is not None:
            return self._fallback
        raise EmbeddingError(_RUNTIME_UNAVAILABLE)

    @property
    def _default_options(self) -> dict[str, Any]:
        fb = self._fallback
        if fb is not None and not isinstance(fb, RuntimeResolvingChatClient):
            return dict(getattr(fb, "_default_options", None) or {})
        if self._resolved_runtime() is not None:
            return dict(getattr(self._delegate(), "_default_options", None) or {})
        return {}

    @property
    def _url(self) -> Any:
        fb = self._fallback
        if fb is not None and not isinstance(fb, RuntimeResolvingChatClient):
            return getattr(fb, "_url", None)
        if self._resolved_runtime() is not None:
            return getattr(self._delegate(), "_url", None)
        return None

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._delegate().chat(*args, **kwargs)

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._delegate().stream_chat(*args, **kwargs)

    def chat_api(self, *args: Any, **kwargs: Any) -> Any:
        return self._delegate().chat_api(*args, **kwargs)

    def chat_api_stream_final(self, *args: Any, **kwargs: Any) -> Any:
        return self._delegate().chat_api_stream_final(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate(), name)


__all__ = [
    "RuntimeBackedEmbeddingProvider",
    "RuntimeBackedRerankClient",
    "RuntimeResolvingChatClient",
]
