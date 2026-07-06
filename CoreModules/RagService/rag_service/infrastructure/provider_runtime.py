"""Provider-runtime backed RAG adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any, Literal

from core.contracts.llm_runtime import LLMRequest
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
    detail = ""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            app = current_app._get_current_object()
            wiring = getattr(app, "extensions", {}).get("llm_proxy_wiring")
            svc = getattr(wiring, "extensions_service", None) if wiring is not None else None
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


class _ProviderScopedChatClient:
    """Thin wrapper that overrides ``_provider_id`` for an existing chat client."""

    __slots__ = ("_inner", "_provider_id")

    def __init__(self, inner: Any, provider_id: str) -> None:
        self._inner = inner
        self._provider_id = provider_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def chat_client_for_provider_id(chat_client: Any, provider_id: str) -> Any:
    pid = str(provider_id or "").strip()
    if not pid:
        return chat_client
    current = str(getattr(chat_client, "_provider_id", "") or "").strip()
    if current == pid:
        return chat_client
    if isinstance(chat_client, RuntimeResolvingChatClient):
        return RuntimeResolvingChatClient(
            runtime_getter=chat_client._runtime_getter,
            runtime=chat_client._runtime,
            provider_id=pid,
            model=chat_client._model,
            fallback=chat_client._fallback,
        )
    return _ProviderScopedChatClient(chat_client, pid)


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
            return _RuntimeBackedChatClient(runtime, provider_id=self._provider_id)
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


class _RuntimeBackedChatClient:
    """Adapter so existing RAG chat-client code can use the shared LLM runtime."""

    def __init__(
        self,
        runtime: Any,
        *,
        provider_id: str,
        upstream_url: str | None = None,
        default_options: dict[str, Any] | None = None,
        delegate: Any | None = None,
    ) -> None:
        self._runtime = runtime
        self._provider_id = provider_id
        self._url = upstream_url
        self._default_options = dict(default_options or {})
        self._delegate = delegate

    def _options(self, options: dict[str, Any] | None) -> dict[str, Any] | None:
        merged = dict(self._default_options)
        merged.update(dict(options or {}))
        return merged or None

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> str:
        if stream:
            parts: list[str] = []
            for kind, data in self.iter_chat_api_stream_events(
                {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": self._options(options) or {},
                    "think": think,
                }
            ):
                if kind in ("thinking_delta", "content_delta") and data:
                    parts.append(str(data))
            return "".join(parts)
        resp = self._runtime.invoke(
            LLMRequest(
                provider_id=self._provider_id,
                model=model,
                operation="chat",
                messages=messages,
                stream=False,
                options=self._options(options),
                think=think,
            )
        )
        return str(resp.text)

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Iterator[str]:
        for kind, data in self.iter_chat_api_stream_events(
            {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": self._options(options) or {},
                "think": think,
            }
        ):
            if kind == "content_delta" and data:
                yield str(data)

    def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._runtime.invoke(
            LLMRequest(
                provider_id=self._provider_id,
                model=str(body.get("model") or ""),
                operation="chat_api",
                body=dict(body),
                stream=bool(body.get("stream", False)),
            )
        )
        return dict(resp.raw or {})

    def chat_api_stream_final(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            fn = getattr(self._delegate, "chat_api_stream_final", None)
            if callable(fn):
                return fn(body)
        except Exception:
            pass
        return self.chat_api({**body, "stream": False})

    def iter_chat_api_stream_events(
        self,
        body: dict[str, Any],
    ) -> Iterator[tuple[str, Any]]:
        for event in self._runtime.stream_invoke(
            LLMRequest(
                provider_id=self._provider_id,
                model=str(body.get("model") or ""),
                operation="chat_api_stream_events",
                body={**body, "stream": True},
                stream=True,
            )
        ):
            yield (str(event.type), event.data)

    def iter_chat_api_stream_openai_parts(
        self,
        body: dict[str, Any],
    ) -> Iterator[tuple[Literal["content", "error"], str]]:
        for kind, data in self.iter_chat_api_stream_events(body):
            if kind in ("thinking_delta", "content_delta"):
                yield ("content", str(data))
            elif kind == "error":
                yield ("error", str(data))

    def __getattr__(self, name: str) -> Any:
        if self._delegate is not None:
            return getattr(self._delegate, name)
        raise AttributeError(name)


__all__ = [
    "RuntimeBackedEmbeddingProvider",
    "RuntimeBackedRerankClient",
    "RuntimeResolvingChatClient",
    "chat_client_for_provider_id",
]
