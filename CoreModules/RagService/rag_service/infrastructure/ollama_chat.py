"""Ollama chat client implementing ChatLLMClient."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from typing import Any, Literal

import requests
from rag_service.config import get_ollama_chat_model, get_ollama_chat_options, get_ollama_chat_url
from rag_service.infrastructure.cli_runner import OllamaInteractorCliError, invoke_chat


def _extract_http_status_from_cli_error(exc: OllamaInteractorCliError) -> int | None:
    """Best-effort HTTP status extraction from interactor stderr/message."""
    stderr = exc.stderr or ""
    msg = str(exc)

    # 1) Structured JSON details (preferred).
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            body = obj.get("body")
            if isinstance(body, dict):
                sc = body.get("status_code")
                try:
                    if sc is not None:
                        n = int(sc)
                        if 400 <= n <= 599:
                            return n
                except (TypeError, ValueError):
                    pass
            for key in ("status_code", "status"):
                try:
                    raw = obj.get(key)
                    if raw is not None:
                        n = int(raw)
                        if 400 <= n <= 599:
                            return n
                except (TypeError, ValueError):
                    pass

    # 2) Common textual patterns.
    blob = f"{msg}\n{stderr}"
    patterns = (
        r"\b([45]\d{2})\s+Server Error\b",
        r"\bstatus(?:_code)?\s*[:=]\s*([45]\d{2})\b",
        r"\bHTTP/\d(?:\.\d)?\s+([45]\d{2})\b",
        r"\b\((4\d{2}|5\d{2})\)\b",
    )
    for pat in patterns:
        m = re.search(pat, blob, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            continue
    return None


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


def _float_env_seconds(name: str, default: float, *, lo: float | None = None, hi: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        v = default
    else:
        try:
            v = float(str(raw).strip())
        except (TypeError, ValueError):
            v = default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def get_ollama_chat_stream_guard_config() -> dict[str, float]:
    """
    HTTP streaming guards for ``/api/chat`` (NDJSON over ``iter_lines``).

    Same env contract as ``infrastructure.ollama.chat_client`` (standalone RagService copy).
    """
    return {
        "connect_timeout_s": _float_env_seconds(
            "OLLAMA_CHAT_STREAM_CONNECT_TIMEOUT_S", 10.0, lo=1.0, hi=300.0
        ),
        "read_timeout_s": _float_env_seconds(
            "OLLAMA_CHAT_STREAM_READ_TIMEOUT_S", 60.0, lo=5.0, hi=7200.0
        ),
        "max_duration_s": _float_env_seconds(
            "OLLAMA_CHAT_STREAM_MAX_DURATION_S", 900.0, lo=0.0, hi=86400.0
        ),
    }


def _chat_runtime_error(use_model: str, url: str, exc: OllamaInteractorCliError) -> RuntimeError:
    sc = _extract_http_status_from_cli_error(exc)
    if sc == 405:
        return RuntimeError(
            f"Ollama endpoint method not allowed (405): {url}. "
            f"This usually means the endpoint doesn't support POST method or the URL is incorrect. "
            f"Model: {use_model}. "
            f"Try checking Ollama API documentation or verify the endpoint URL."
        )
    if sc == 404:
        return RuntimeError(
            f"Ollama endpoint not found (404): {url}. "
            f"Please check if Ollama is running and the URL is correct. "
            f"Model: {use_model}"
        )
    if sc is not None and 500 <= sc <= 599:
        return RuntimeError(
            f"Ollama upstream error (HTTP {sc}) for model {use_model} via {url}. "
            f"This is usually a temporary upstream/network issue; retry may succeed. Original: {exc}"
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
        _guard = get_ollama_chat_stream_guard_config()
        _http_timeout = (_guard["connect_timeout_s"], _guard["read_timeout_s"])
        try:
            resp = requests.post(self._url, json=payload, timeout=_http_timeout, stream=True)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            snippet = ""
            if e.response is not None:
                try:
                    snippet = (e.response.text or "").strip()[:800]
                except Exception:
                    snippet = ""
            extra = f" {snippet}" if snippet else ""
            raise RuntimeError(
                f"Ollama chat stream API error (model={use_model}, url={self._url}): {e}{extra}"
            ) from e
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

    def iter_chat_api_stream_events(
        self,
        body: dict[str, Any],
    ) -> Iterator[tuple[str, Any]]:
        """
        Stream /api/chat over HTTP; yield structured events:

        - ``("thinking_delta", str)`` -- thinking text delta
        - ``("content_delta", str)`` -- final answer text delta
        - ``("tool_calls", list)``   -- tool calls from Ollama (at end of stream)
        - ``("done", dict)``         -- final metrics (eval_count, eval_duration, etc.)
        - ``("error", str)``         -- error message
        """
        use_model = str(body.get("model") or self._model)
        payload = {**body, "stream": True}
        opts = normalize_ollama_chat_options(
            {**(self._default_options or {}), **(payload.get("options") or {})}
        )
        payload["options"] = opts
        _guard = get_ollama_chat_stream_guard_config()
        _http_timeout = (_guard["connect_timeout_s"], _guard["read_timeout_s"])
        _max_wall_s = float(_guard["max_duration_s"])
        try:
            resp = requests.post(self._url, json=payload, timeout=_http_timeout, stream=True)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            snippet = ""
            if e.response is not None:
                try:
                    snippet = (e.response.text or "").strip()[:800]
                except Exception:
                    snippet = ""
            extra = f" {snippet}" if snippet else ""
            yield ("error", f"Ollama chat stream API error (model={use_model}, url={self._url}): {e}{extra}")
            return
        except requests.exceptions.RequestException as e:
            yield ("error", f"Ollama chat stream API error (model={use_model}, url={self._url}): {e}")
            return
        merged: dict[str, Any] = {}
        prev_th = ""
        prev_co = ""
        saw_done = False
        stream_aborted = False
        t0 = time.monotonic()
        try:
            try:
                for line in resp.iter_lines(decode_unicode=True):
                    if _max_wall_s > 0.0 and (time.monotonic() - t0) > _max_wall_s:
                        yield (
                            "error",
                            (
                                f"Ollama chat stream exceeded max wall duration ({int(_max_wall_s)}s) "
                                f"(model={use_model}, url={self._url})."
                            ),
                        )
                        stream_aborted = True
                        break
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
                        stream_aborted = True
                        break
                    m = obj.get("message")
                    if isinstance(m, dict):
                        merged = _merge_ollama_assistant_message_parts(merged, m)
                    th = merged.get("thinking") if isinstance(merged.get("thinking"), str) else ""
                    co = merged.get("content") if isinstance(merged.get("content"), str) else ""
                    if th.startswith(prev_th) and len(th) >= len(prev_th):
                        suffix = th[len(prev_th):]
                        if suffix:
                            yield ("thinking_delta", suffix)
                        prev_th = th
                    elif th != prev_th:
                        if th:
                            yield ("thinking_delta", th)
                        prev_th = th
                    if co.startswith(prev_co) and len(co) >= len(prev_co):
                        suffix_c = co[len(prev_co):]
                        if suffix_c:
                            yield ("content_delta", suffix_c)
                        prev_co = co
                    elif co != prev_co:
                        if co:
                            yield ("content_delta", co)
                        prev_co = co
                    if obj.get("done"):
                        saw_done = True
                        tc = merged.get("tool_calls")
                        if isinstance(tc, list) and tc:
                            yield ("tool_calls", tc)
                        metrics = {
                            k: v for k, v in obj.items()
                            if k not in ("message", "model", "done", "created_at") and v is not None
                        }
                        metrics["_merged_message"] = dict(merged)
                        yield ("done", metrics)
                        break
            except requests.exceptions.ReadTimeout:
                yield (
                    "error",
                    (
                        f"Ollama chat stream read idle timeout (>{int(_guard['read_timeout_s'])}s without data) "
                        f"(model={use_model}, url={self._url})."
                    ),
                )
                stream_aborted = True
        finally:
            resp.close()
        if not saw_done and not stream_aborted:
            yield (
                "error",
                (
                    f"Ollama chat stream ended without a terminal done chunk (model={use_model}, url={self._url})."
                ),
            )

    def iter_chat_api_stream_openai_parts(
        self,
        body: dict[str, Any],
    ) -> Iterator[tuple[Literal["content", "error"], str]]:
        """
        Stream /api/chat over HTTP; yield a single visible text stream with thinking first and
        final answer second. Delegates to ``iter_chat_api_stream_events``.
        """
        for kind, data in self.iter_chat_api_stream_events(body):
            if kind in ("thinking_delta", "content_delta"):
                yield ("content", data)
            elif kind == "error":
                yield ("error", data)


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
