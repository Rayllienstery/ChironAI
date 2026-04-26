"""
Ollama chat client implementing ChatLLMClient.

Calls Ollama via ollama_interactor CLI (subprocess).
"""

from __future__ import annotations

import json
import os
import time
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

    - ``connect_timeout_s`` / ``read_timeout_s`` → ``requests`` ``timeout=(connect, read)`` per read.
    - ``max_duration_s``: wall-clock cap between successful line reads; ``0`` disables.

    Env: ``OLLAMA_CHAT_STREAM_CONNECT_TIMEOUT_S`` (default 10),
    ``OLLAMA_CHAT_STREAM_READ_TIMEOUT_S`` (default 60),
    ``OLLAMA_CHAT_STREAM_MAX_DURATION_S`` (default 900; ``0`` = no cap).
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


def _non_empty_str(value: Any) -> str:
    if isinstance(value, str):
        s = value.strip()
        if s:
            return s
    return ""


def _tool_call_signature(call: dict[str, Any]) -> str:
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    candidates = []
    if isinstance(fn, dict):
        candidates.extend((fn.get("thought_signature"), fn.get("thoughtSignature")))
    candidates.extend((call.get("thought_signature"), call.get("thoughtSignature")))
    extra = call.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google")
        if isinstance(google, dict):
            candidates.extend((google.get("thought_signature"), google.get("thoughtSignature")))
    for raw in candidates:
        s = _non_empty_str(raw)
        if s:
            return s
    return ""


def _tool_call_key(call: dict[str, Any], idx: int) -> str:
    cid = _non_empty_str(call.get("id")) or _non_empty_str(call.get("call_id"))
    if cid:
        return f"id:{cid}"
    fn = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = _non_empty_str(fn.get("name") if isinstance(fn, dict) else None).lower()
    fn_index = None
    if isinstance(fn, dict):
        fn_index = fn.get("index")
    if fn_index is None:
        fn_index = call.get("index")
    if name and fn_index is not None:
        try:
            return f"idx_name:{int(fn_index)}:{name}"
        except (TypeError, ValueError):
            return f"idx_name:{fn_index}:{name}"
    if name:
        return f"name:{name}"
    return f"pos:{idx}"


def _tool_arguments_substantive(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _merge_single_tool_call(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    for k, v in incoming.items():
        if k in {"id", "call_id", "function", "extra_content"}:
            continue
        if v is not None:
            out[k] = v

    existing_fn = existing.get("function") if isinstance(existing.get("function"), dict) else {}
    incoming_fn = incoming.get("function") if isinstance(incoming.get("function"), dict) else {}
    fn_out = dict(existing_fn)
    for k, v in incoming_fn.items():
        if k == "arguments":
            if _tool_arguments_substantive(v) or "arguments" not in fn_out:
                fn_out["arguments"] = v
            continue
        if k in {"name", "thought_signature", "thoughtSignature"}:
            s = _non_empty_str(v)
            if s or k not in fn_out:
                if s:
                    target_key = "thought_signature" if "thought" in k.lower() else "name"
                    fn_out[target_key] = s
            continue
        if v is not None:
            fn_out[k] = v

    name = _non_empty_str(fn_out.get("name")) or _non_empty_str(existing_fn.get("name")) or _non_empty_str(
        incoming_fn.get("name")
    )
    if name:
        fn_out["name"] = name

    sig = _tool_call_signature(incoming) or _tool_call_signature(existing)
    if sig:
        fn_out["thought_signature"] = sig

    out["function"] = fn_out

    id_value = _non_empty_str(incoming.get("id")) or _non_empty_str(existing.get("id"))
    call_id_value = _non_empty_str(incoming.get("call_id")) or _non_empty_str(existing.get("call_id"))
    canonical = id_value or call_id_value
    if canonical:
        out["id"] = canonical
        out["call_id"] = call_id_value or canonical

    existing_extra = existing.get("extra_content") if isinstance(existing.get("extra_content"), dict) else {}
    incoming_extra = incoming.get("extra_content") if isinstance(incoming.get("extra_content"), dict) else {}
    extra_out = dict(existing_extra)
    for k, v in incoming_extra.items():
        if v is None:
            continue
        if k == "google" and isinstance(v, dict):
            google_prev = extra_out.get("google")
            google_out = dict(google_prev) if isinstance(google_prev, dict) else {}
            for gk, gv in v.items():
                if gv is not None:
                    google_out[gk] = gv
            extra_out["google"] = google_out
            continue
        extra_out[k] = v
    if sig:
        google_prev = extra_out.get("google")
        google_out = dict(google_prev) if isinstance(google_prev, dict) else {}
        google_out.setdefault("thought_signature", sig)
        extra_out["google"] = google_out
    if extra_out:
        out["extra_content"] = extra_out

    if not _non_empty_str(out.get("type")):
        out["type"] = "function"
    return out


def _merge_tool_calls(existing_calls: list[Any], incoming_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}

    for idx, raw in enumerate(existing_calls):
        if not isinstance(raw, dict):
            continue
        item = _merge_single_tool_call({}, raw)
        key = _tool_call_key(item, idx)
        key_to_index[key] = len(out)
        out.append(item)

    for idx, raw in enumerate(incoming_calls):
        if not isinstance(raw, dict):
            continue
        item = _merge_single_tool_call({}, raw)
        key = _tool_call_key(item, idx)
        existing_idx = key_to_index.get(key)
        if existing_idx is None:
            key_to_index[key] = len(out)
            out.append(item)
            continue
        out[existing_idx] = _merge_single_tool_call(out[existing_idx], item)

    return out


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
        elif k == "tool_calls":
            if not isinstance(v, list) or not v:
                continue
            prev_calls = out.get("tool_calls") if isinstance(out.get("tool_calls"), list) else []
            out["tool_calls"] = _merge_tool_calls(prev_calls, v)
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


__all__ = ["OllamaChatClient", "get_ollama_chat_stream_guard_config"]
