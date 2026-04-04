"""
Ollama chat client implementing ChatLLMClient.

Calls Ollama via ollama_interactor CLI (subprocess).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

try:
    from config import get_ollama_chat_model, get_ollama_chat_url, get_ollama_chat_options
except ImportError:
    get_ollama_chat_url = lambda: "http://localhost:11434/api/chat"  # type: ignore
    # When config is not importable, treat model as unset; callers must validate.
    get_ollama_chat_model = lambda: ""  # type: ignore
    get_ollama_chat_options = lambda: {"num_predict": 3072, "temperature": 0.0, "top_p": 1.0}  # type: ignore

import requests

from infrastructure.ollama.cli_runner import OllamaInteractorCliError, invoke_chat


def normalize_ollama_chat_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """
    Ollama (including cloud models) returns 400 for greedy sampling (temperature <= 0)
    combined with top_p < 1: "top_p must be 1 when using greedy sampling."
    """
    if not options:
        return {}
    out = dict(options)
    try:
        t = float(out["temperature"])
    except (KeyError, TypeError, ValueError):
        return out
    if t > 0.0:
        return out
    try:
        tp = float(out.get("top_p", 1.0))
    except (TypeError, ValueError):
        out["top_p"] = 1.0
        return out
    if tp < 1.0:
        out["top_p"] = 1.0
    return out


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
        think: bool | str | None = None,
    ) -> str:
        """Send messages and return the assistant reply. Non-stream only for string return."""
        use_model = model or self._model
        opts = normalize_ollama_chat_options(
            {**(self._default_options or {}), **(options or {})}
        )
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": opts,
        }
        if think is not None:
            payload["think"] = think
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

    def chat_api(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        POST /api/chat with an arbitrary JSON body (e.g. tools, stream flag).
        Returns the parsed top-level JSON object.
        """
        use_model = str(body.get("model") or self._model)
        payload = {**body}
        payload["options"] = normalize_ollama_chat_options(
            dict(payload.get("options") or {})
        )
        stdin_obj: dict[str, Any] = {"url": self._url, "json": payload, "timeout": 600}
        try:
            return invoke_chat(stdin_obj, default_timeout=600)
        except OllamaInteractorCliError as e:
            raise _chat_runtime_error(use_model, self._url, e) from e

    def chat_api_stream_final(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        Streaming /api/chat: read NDJSON lines and build a non-stream-shaped response.

        Ollama streams partial ``message`` fields; the last chunk with ``done: true`` may omit
        fields that appeared only in earlier chunks, so we merge every ``message`` update.
        """
        use_model = str(body.get("model") or self._model)
        payload = {**body, "stream": True}
        opts = normalize_ollama_chat_options(
            {**(self._default_options or {}), **(payload.get("options") or {})}
        )
        payload["options"] = opts
        try:
            resp = requests.post(self._url, json=payload, timeout=600, stream=True)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama chat stream API error (model={use_model}, url={self._url}): {e}") from e
        try:
            return _aggregate_ollama_chat_stream_response(resp)
        finally:
            resp.close()

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Iterator[str]:
        """Stream chat: yield text chunks from Ollama (thinking and content merged into one stream)."""
        use_model = model or self._model
        opts = normalize_ollama_chat_options(
            {**(self._default_options or {}), **(options or {})}
        )
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "stream": True,
            "options": opts,
        }
        if think is not None:
            payload["think"] = think
        for kind, text in self.iter_chat_api_stream_openai_parts(payload):
            if kind == "content":
                yield text

    def iter_chat_api_stream_openai_parts(
        self,
        body: dict[str, Any],
    ) -> Iterator[tuple[Literal["content", "error"], str]]:
        """
        Stream /api/chat over HTTP; yield (\"content\", delta) for both thinking and content suffixes
        (single visible stream). Uses cumulative merge + suffix deltas.
        """
        use_model = str(body.get("model") or self._model)
        payload = {**body, "stream": True}
        opts = normalize_ollama_chat_options(
            {**(self._default_options or {}), **(payload.get("options") or {})}
        )
        payload["options"] = opts
        try:
            resp = requests.post(self._url, json=payload, timeout=600, stream=True)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            yield ("error", f"Ollama chat stream API error (model={use_model}, url={self._url}): {e}")
            return
        merged: dict[str, Any] = {}
        prev_th = ""
        prev_co = ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not str(line).strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("error") is not None:
                    yield ("error", str(obj.get("error")))
                    return
                m = obj.get("message")
                if isinstance(m, dict):
                    merged = _merge_ollama_assistant_message_parts(merged, m)
                th = merged.get("thinking") if isinstance(merged.get("thinking"), str) else ""
                co = merged.get("content") if isinstance(merged.get("content"), str) else ""
                if th.startswith(prev_th) and len(th) >= len(prev_th):
                    suffix = th[len(prev_th) :]
                    if suffix:
                        yield ("content", suffix)
                    prev_th = th
                elif th != prev_th:
                    if th:
                        yield ("content", th)
                    prev_th = th
                if co.startswith(prev_co) and len(co) >= len(prev_co):
                    suffix_c = co[len(prev_co) :]
                    if suffix_c:
                        yield ("content", suffix_c)
                    prev_co = co
                elif co != prev_co:
                    if co:
                        yield ("content", co)
                    prev_co = co
        finally:
            resp.close()


def _merge_ollama_assistant_message_parts(acc: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    """Merge streamed assistant ``message`` fragments (later chunks override when non-empty)."""
    out = dict(acc)
    for k, v in chunk.items():
        if k == "content":
            if v is None:
                continue
            if isinstance(v, str) and not v.strip() and out.get("content"):
                continue
            out[k] = v
        elif k == "thinking":
            if v is None:
                continue
            if isinstance(v, str) and not v.strip() and out.get("thinking"):
                continue
            out[k] = v
        elif k == "tool_calls" and v:
            out[k] = v
        elif v is not None and k not in ("content", "tool_calls", "thinking"):
            out[k] = v
    return out


def _aggregate_ollama_chat_stream_response(resp: Any) -> dict[str, Any]:
    """Parse Ollama /api/chat NDJSON stream into one dict like a non-streaming API response."""
    merged_message: dict[str, Any] = {}
    last_done: dict[str, Any] | None = None
    last_any: dict[str, Any] | None = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not str(line).strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("error") is not None:
            return {"error": str(obj.get("error"))}
        last_any = obj
        m = obj.get("message")
        if isinstance(m, dict):
            merged_message = _merge_ollama_assistant_message_parts(merged_message, m)
        if obj.get("done"):
            last_done = obj

    if last_done:
        out = dict(last_done)
        lm = last_done.get("message") if isinstance(last_done.get("message"), dict) else {}
        final_msg = _merge_ollama_assistant_message_parts(merged_message, lm)
        if not final_msg.get("content") and not final_msg.get("tool_calls") and merged_message:
            final_msg = merged_message
        out["message"] = final_msg
        return out
    if merged_message:
        return {"message": merged_message, "done": True}
    return last_any or {}


__all__ = ["OllamaChatClient"]
