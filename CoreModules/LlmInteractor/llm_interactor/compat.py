"""Compatibility adapter exposing a chat-client-like interface over the blind runtime."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal

from llm_interactor.contracts import LLMRequest
from llm_interactor.runtime import LLMRuntime


class RuntimeBackedChatClient:
    """Adapter so existing proxy code can keep calling chat_client-like methods."""

    def __init__(
        self,
        runtime: LLMRuntime,
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
        return resp.text

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
