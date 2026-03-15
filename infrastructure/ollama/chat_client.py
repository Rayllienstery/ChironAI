"""
Ollama chat client implementing ChatLLMClient.

Maps HTTP/requests errors to domain errors.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests

try:
    from config import get_ollama_chat_model, get_ollama_chat_url, get_ollama_chat_options
except ImportError:
    get_ollama_chat_url = lambda: "http://localhost:11434/api/chat"  # type: ignore
    get_ollama_chat_model = lambda: "danielsheep/gpt-oss-20b-unsloth:UD-Q6_K_XL"  # type: ignore
    get_ollama_chat_options = lambda: {"num_predict": 3072, "temperature": 0.0, "top_p": 0.1}  # type: ignore


class OllamaChatClient:
    """Chat LLM client using Ollama /api/chat."""

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
        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": opts,
        }
        try:
            resp = requests.post(
                self._url,
                json=payload,
                stream=stream,
                timeout=600,
            )
            resp.raise_for_status()
            data = resp.json()
            if stream:
                # Caller may consume stream; we don't return full string for stream.
                return ""
            msg = data.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            return (content or "").strip()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 405:
                raise RuntimeError(
                    f"Ollama endpoint method not allowed (405): {self._url}. "
                    f"This usually means the endpoint doesn't support POST method or the URL is incorrect. "
                    f"Model: {use_model}. "
                    f"Try checking Ollama API documentation or verify the endpoint URL."
                ) from e
            raise RuntimeError(
                f"Ollama chat API error (model={use_model}, url={self._url}, status={e.response.status_code}): {e}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"Ollama chat API error (model={use_model}, url={self._url}): {e}"
            ) from e

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """Stream chat: yield content chunks from Ollama NDJSON stream."""
        use_model = model or self._model
        opts = {**(self._default_options or {}), **(options or {})}
        payload = {
            "model": use_model,
            "messages": messages,
            "stream": True,
            "options": opts,
        }
        try:
            resp = requests.post(
                self._url,
                json=payload,
                stream=True,
                timeout=600,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise RuntimeError(
                    f"Ollama endpoint not found (404): {self._url}. "
                    f"Please check if Ollama is running and the URL is correct. "
                    f"Model: {use_model}"
                ) from e
            elif e.response.status_code == 405:
                raise RuntimeError(
                    f"Ollama endpoint method not allowed (405): {self._url}. "
                    f"This usually means the endpoint doesn't support POST method or the URL is incorrect. "
                    f"Model: {use_model}. "
                    f"Try checking Ollama API documentation or verify the endpoint URL."
                ) from e
            raise RuntimeError(
                f"Ollama chat API error (model={use_model}, url={self._url}, status={e.response.status_code}): {e}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"Ollama chat API error (model={use_model}, url={self._url}): {e}"
            ) from e
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                import json as _json
                obj = _json.loads(line)
            except Exception:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content", "")
            if content:
                yield content


__all__ = ["OllamaChatClient"]
