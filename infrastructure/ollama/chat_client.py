"""
Ollama chat client implementing ChatLLMClient.

Calls Ollama via ollama_interactor CLI (subprocess).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

try:
    from config import get_ollama_chat_model, get_ollama_chat_url, get_ollama_chat_options
except ImportError:
    get_ollama_chat_url = lambda: "http://localhost:11434/api/chat"  # type: ignore
    get_ollama_chat_model = lambda: "danielsheep/gpt-oss-20b-unsloth:UD-Q6_K_XL"  # type: ignore
    get_ollama_chat_options = lambda: {"num_predict": 3072, "temperature": 0.0, "top_p": 0.1}  # type: ignore

from infrastructure.ollama.cli_runner import OllamaInteractorCliError, invoke_chat, iter_chat_stream


def _chat_runtime_error(use_model: str, url: str, exc: OllamaInteractorCliError) -> RuntimeError:
    msg = str(exc)
    if "405" in msg or (exc.stderr and "405" in exc.stderr):
        return RuntimeError(
            f"Ollama endpoint method not allowed (405): {url}. "
            f"This usually means the endpoint doesn't support POST method or the URL is incorrect. "
            f"Model: {use_model}. "
            f"Try checking Ollama API documentation or verify the endpoint URL."
        )
    if "404" in msg or (exc.stderr and "404" in exc.stderr):
        return RuntimeError(
            f"Ollama endpoint not found (404): {url}. "
            f"Please check if Ollama is running and the URL is correct. "
            f"Model: {use_model}"
        )
    return RuntimeError(f"Ollama chat API error (model={use_model}, url={url}): {exc}")


class OllamaChatClient:
    """Chat LLM client using Ollama /api/chat via CLI."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        default_options: dict[str, Any] | None = None,
    ) -> None:
        self._url = base_url or get_ollama_chat_url()
        self._model = model or get_ollama_chat_model()
        self._default_options = default_options or get_ollama_chat_options()

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool = False,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Send messages and return the assistant reply. Non-stream only for string return."""
        use_model = model or self._model
        opts = {**(self._default_options or {}), **(options or {})}
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": opts,
        }
        if stream:
            return ""
        stdin_obj: dict[str, Any] = {"url": self._url, "json": payload, "timeout": 600}
        try:
            data = invoke_chat(stdin_obj, default_timeout=600)
            msg = data.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            return (content or "").strip()
        except OllamaInteractorCliError as e:
            raise _chat_runtime_error(use_model, self._url, e) from e

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Stream chat: yield content chunks from Ollama NDJSON stream via CLI."""
        use_model = model or self._model
        opts = {**(self._default_options or {}), **(options or {})}
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "stream": True,
            "options": opts,
        }
        stdin_obj: dict[str, Any] = {"url": self._url, "json": payload, "timeout": 600}
        try:
            yield from iter_chat_stream(stdin_obj, default_timeout=600)
        except OllamaInteractorCliError as e:
            raise _chat_runtime_error(use_model, self._url, e) from e


__all__ = ["OllamaChatClient"]
