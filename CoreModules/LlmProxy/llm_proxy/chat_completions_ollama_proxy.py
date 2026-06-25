"""Ollama /api/chat proxy helpers and trace-friendly message snapshots."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

from llm_proxy.chat_completions_upstream_budget import _ollama_message_content_str
from llm_proxy.ollama_compat import (
    caps_supports_thinking,
    ollama_chat_tool_choice_payload_value,
    resolve_brand_key,
)

_OLLAMA_TRACE_MSG_PREVIEW = 300
_OLLAMA_TRACE_MSG_FULL_CAP = 32_768


def _trace_ollama_messages_for_ui(ollama_messages: list[Any]) -> list[dict[str, Any]]:
    """Snapshots messages for Proxy Trace (preview + capped full text for the WebUI modal)."""
    cap = max(4096, int(_OLLAMA_TRACE_MSG_FULL_CAP))
    out: list[dict[str, Any]] = []
    for m in ollama_messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role") or ""
        _raw_content = m.get("content")
        content_str = _ollama_message_content_str(_raw_content)
        content_len = len(content_str)
        lim = _OLLAMA_TRACE_MSG_PREVIEW
        truncated = content_len > cap
        displayed_full = content_str[:cap] + (f"... [truncated {content_len - cap} chars]" if truncated else "")
        entry: dict[str, Any] = {
            "role": str(role),
            "content_length_chars": int(content_len),
            "content_preview": content_str[:lim] + ("..." if content_len > lim else ""),
            "content_full": displayed_full,
        }
        if truncated:
            entry["content_full_was_truncated"] = True
        thinking = m.get("thinking")
        if isinstance(thinking, str) and thinking:
            entry["thinking_length_chars"] = len(thinking)
            entry["thinking_preview"] = thinking[:lim] + ("..." if len(thinking) > lim else "")
        _imgs = m.get("images")
        if isinstance(_imgs, list) and _imgs:
            entry["images_count"] = len(_imgs)
        out.append(entry)
    return out


def _trace_ollama_api_metrics(src: dict[str, Any] | None, model_id: str | None = None) -> dict[str, Any]:
    """Top-level Ollama /api/chat fields useful for diagnosing stop vs length truncation."""
    if not isinstance(src, dict):
        return {}
    out: dict[str, Any] = {}
    if src.get("done_reason") is not None:
        out["ollama_done_reason"] = src["done_reason"]
    for k in ("eval_count", "prompt_eval_count"):
        if src.get(k) is not None:
            out[f"ollama_{k}"] = src[k]
            out[k] = src[k]
    if model_id:
        brand_key = resolve_brand_key(model_id, show_payload=src)
        if brand_key:
            out["brand_key"] = brand_key
    return out


def _apply_provider_trace_fields(
    trace: dict[str, Any],
    chat_client: Any,
    *,
    model_id: str,
    operation: str,
) -> None:
    """Record the provider-runtime boundary used for the upstream chat call."""
    ollama = trace.setdefault("ollama", {})
    request = trace.setdefault("request", {})
    provider_id = str(getattr(chat_client, "_provider_id", "") or "").strip()
    if provider_id:
        ollama["provider_id"] = provider_id
        request["provider_id"] = provider_id
    if model_id:
        ollama["provider_model_id"] = str(model_id)
    if operation:
        ollama["provider_operation"] = str(operation)
    if provider_id or getattr(chat_client, "_runtime", None) is not None:
        ollama["provider_runtime"] = True


def _merge_ollama_visible_text(thinking: str | None, content: str | None) -> str:
    """Single trace string: thinking then content when both exist."""
    t = (thinking or "").strip()
    c = (content or "").strip()
    if t and c:
        return f"{t}\n\n{c}"
    return c or t


def _assistant_text_parts(
    thinking: str | None,
    content: str | None,
) -> dict[str, str]:
    reasoning_content = (thinking or "").strip()
    final_content = (content or "").strip()
    return {
        "visible_content": _merge_ollama_visible_text(reasoning_content, final_content),
        "reasoning_content": reasoning_content,
        "final_content": final_content,
    }


def _assistant_text_parts_from_ollama_message(ollama_msg: dict[str, Any]) -> dict[str, str]:
    content = ollama_msg.get("content") if isinstance(ollama_msg.get("content"), str) else ""
    thinking = ollama_msg.get("thinking") if isinstance(ollama_msg.get("thinking"), str) else ""
    return _assistant_text_parts(thinking, content)


def _text_preview(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _apply_trace_response_text_fields(
    response: dict[str, Any],
    *,
    visible_content: str,
    reasoning_content: str,
    final_content: str,
    log_preview: int,
) -> None:
    response["content_preview"] = _text_preview(visible_content, log_preview)
    response["content_length_chars"] = len(visible_content)
    response["has_reasoning"] = bool(reasoning_content.strip())
    response["reasoning_preview"] = _text_preview(reasoning_content, log_preview)
    response["final_content_preview"] = _text_preview(final_content, log_preview)
    response["reasoning_chars"] = len(reasoning_content)
    response["final_content_chars"] = len(final_content)


def _positive_int_or_none(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _effective_num_predict(
    chat_client: Any,
    build_extra_options: dict[str, Any],
    chat_max_tokens: int | None,
) -> int | None:
    build_n = _positive_int_or_none(build_extra_options.get("num_predict"))
    if chat_max_tokens is not None:
        return min(chat_max_tokens, build_n) if build_n is not None else chat_max_tokens
    if build_n is not None:
        return build_n
    default_options = getattr(chat_client, "_default_options", None)
    if isinstance(default_options, dict):
        return _positive_int_or_none(default_options.get("num_predict"))
    return None


def _effective_num_ctx(
    chat_client: Any,
    build_extra_options: dict[str, Any],
) -> int | None:
    n = _positive_int_or_none(build_extra_options.get("num_ctx"))
    if n is not None:
        return n
    default_options = getattr(chat_client, "_default_options", None)
    if isinstance(default_options, dict):
        return _positive_int_or_none(default_options.get("num_ctx"))
    return None


def _effective_max_agent_steps(active_build: dict[str, Any] | None) -> int | None:
    if not isinstance(active_build, dict):
        return None
    n = _positive_int_or_none(active_build.get("max_agent_steps"))
    if n is None:
        return None
    return max(1, min(n, 256))


def _input_budget_from_context(
    *,
    num_ctx: int | None,
    num_predict: int | None,
) -> dict[str, int] | None:
    if num_ctx is None or num_ctx <= 0 or num_predict is None or num_predict <= 0:
        return None
    safety_margin = max(4096, min(int(num_ctx / 32), 8192))
    input_budget = max(1024, int(num_ctx) - int(num_predict) - safety_margin)
    return {
        "num_ctx": int(num_ctx),
        "reserved_output_tokens": int(num_predict),
        "safety_margin_tokens": int(safety_margin),
        "input_budget_tokens": int(input_budget),
        "input_budget_json_chars": int(input_budget * 4),
    }


def _append_trace_warning(trace: dict[str, Any], code: str) -> None:
    warnings = trace.setdefault("warnings", [])
    if isinstance(warnings, list) and code not in warnings:
        warnings.append(code)


_QDRANT_COLLECTION_NAMES_CACHE: dict[str, tuple[float, set[str], str | None]] = {}


def _qdrant_collection_names_cached(qdrant_url: str, *, timeout_s: float = 0.8) -> tuple[set[str], str | None]:
    url = str(qdrant_url or "").strip().rstrip("/")
    if not url:
        return set(), "qdrant_url_missing"
    if not url.startswith(("http://", "https://")):
        return set(), "qdrant_url_invalid_scheme"
    now = time.time()
    cached = _QDRANT_COLLECTION_NAMES_CACHE.get(url)
    if cached is not None:
        ts, names, error = cached
        if now - ts <= 5.0:
            return set(names), error
    try:
        collections_url = f"{url}/collections"
        with urllib.request.urlopen(collections_url, timeout=timeout_s) as resp:  # nosec B310
            raw = resp.read()
        data = json.loads(raw.decode("utf-8")) if raw else {}
        collections = ((data.get("result") or {}).get("collections") or [])
        names = {
            str(item.get("name") or "").strip()
            for item in collections
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        _QDRANT_COLLECTION_NAMES_CACHE[url] = (now, names, None)
        return set(names), None
    except Exception as exc:
        error = str(exc)
        _QDRANT_COLLECTION_NAMES_CACHE[url] = (now, set(), error)
        return set(), error


def _effective_rag_collection_name(rag_repo: Any) -> str:
    getter = getattr(rag_repo, "get_collection_name", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "").strip()
    except Exception:
        return ""


def _build_rag_collection_issue(
    *,
    collection_name: str,
    collection_source: str,
    qdrant_url: str,
) -> dict[str, Any] | None:
    names, error = _qdrant_collection_names_cached(qdrant_url)
    if error:
        return None
    if not names:
        return {
            "code": "rag_collection_not_selected",
            "title": "RAG collection is not selected",
            "message": "Qdrant has no available collections. Create or select a collection in RAG / Qdrant before using RAG.",
            "collection_name": collection_name,
            "collection_source": collection_source,
            "available_collections": [],
        }
    if not collection_name:
        return {
            "code": "rag_collection_not_selected",
            "title": "RAG collection is not selected",
            "message": "Choose a Qdrant collection in RAG / Qdrant before using RAG.",
            "collection_name": "",
            "collection_source": collection_source,
            "available_collections": sorted(names),
        }
    if collection_name not in names:
        return {
            "code": "rag_collection_missing",
            "title": "RAG collection is unavailable",
            "message": (
                f"Configured collection '{collection_name}' is not in Qdrant. "
                "Choose an available collection in RAG / Qdrant."
            ),
            "collection_name": collection_name,
            "collection_source": collection_source,
            "available_collections": sorted(names),
        }
    return None


def _apply_response_diagnostics(trace: dict[str, Any]) -> None:
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
    tool_calls_count = _positive_int_or_none(resp.get("tool_calls_count")) or 0
    reasoning_chars = _positive_int_or_none(resp.get("reasoning_chars")) or 0
    final_content_chars = _positive_int_or_none(resp.get("final_content_chars")) or 0
    if reasoning_chars > 0 and final_content_chars == 0 and tool_calls_count == 0:
        _append_trace_warning(trace, "reasoning_only_response")

    effective = _positive_int_or_none(req.get("effective_num_predict"))
    eval_count = _positive_int_or_none(resp.get("ollama_eval_count"))
    if eval_count is None:
        eval_count = _positive_int_or_none(resp.get("eval_count"))
    if effective is not None and eval_count is not None and eval_count >= effective:
        _append_trace_warning(trace, "output_token_budget_exhausted")


def _output_budget_eval_count(
    trace: dict[str, Any],
    metrics_src: dict[str, Any] | None = None,
) -> tuple[int | None, int | None]:
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    effective = _positive_int_or_none(req.get("effective_num_predict"))
    if effective is None:
        return None, None
    eval_count = None
    if isinstance(metrics_src, dict):
        eval_count = _positive_int_or_none(metrics_src.get("eval_count"))
        if eval_count is None:
            eval_count = _positive_int_or_none(metrics_src.get("ollama_eval_count"))
    if eval_count is None:
        resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
        eval_count = _positive_int_or_none(resp.get("ollama_eval_count"))
        if eval_count is None:
            eval_count = _positive_int_or_none(resp.get("eval_count"))
    return effective, eval_count


def _output_budget_is_exhausted(trace: dict[str, Any], metrics_src: dict[str, Any] | None = None) -> bool:
    effective, eval_count = _output_budget_eval_count(trace, metrics_src)
    if effective is None or eval_count is None:
        return False
    return eval_count >= effective


def _output_budget_exhaustion_error(trace: dict[str, Any], metrics_src: dict[str, Any] | None = None) -> str:
    effective, eval_count = _output_budget_eval_count(trace, metrics_src)
    if effective is None or eval_count is None or eval_count < effective:
        return ""
    return (
        f"[Error: output token budget exhausted: generated {eval_count} tokens reached "
        f"num_predict={effective}. Increase Model Build num_predict/max_tokens or shorten the prompt.]"
    )


def passthrough_think_from_body(body: dict[str, Any]) -> bool | str | None:
    """Pass Ollama ``think`` only when the client included the key (mediator; no derived mapping)."""
    if "think" not in body:
        return None
    raw = body.get("think")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
    return None


def _ollama_native_think_broken_for_model(model_name: str | None) -> bool:
    """Ollama native ``think`` with Qwen3 often returns only placeholder output (e.g. ``.``).

    Only matches the ``qwen3`` family (qwen3, qwen3:7b, etc.), NOT newer
    versions like ``qwen3.5``, ``qwen3.1`` where thinking works correctly.
    """
    name = (model_name or "").lower()
    idx = name.find("qwen3")
    if idx < 0:
        return False
    after = idx + 5  # position right after "qwen3"
    return not (after < len(name) and name[after] in ".0123456789")


def effective_ollama_think_from_body(
    body: dict[str, Any],
    ollama_model: str | None,
    *,
    capabilities: frozenset[str] | None = None,
) -> bool | str | None:
    """
    Value actually sent to Ollama ``/api/chat``.

    For the original Qwen3 family, omitting ``think`` often leaves the model's template with
    thinking enabled by default, which yields placeholder-only output.  Always send explicit
    ``think: false`` for those models.  Newer versions (qwen3.5, qwen3.1, …) are not affected.
    For other models, passthrough only when the client sent ``think`` (mediator).
    When ``capabilities`` is known and excludes thinking, omit ``think`` so Ollama uses model defaults.
    """
    raw = passthrough_think_from_body(body)
    if _ollama_native_think_broken_for_model(ollama_model):
        return False
    if capabilities is not None and raw is not None and not caps_supports_thinking(capabilities):
        return None
    return raw


def gpt_oss_model_requires_reasoning_level(model_name: str | None) -> bool:
    return "gpt-oss" in (model_name or "").lower()


_PLACEHOLDER_REPLY_FALLBACK_EN = (
    "The model returned only a placeholder fragment. Try again, shorten the prompt, or switch model. "
    "The system prompt already prioritizes your message and attachments over retrieved snippets."
)


def _is_placeholder_only_reply(text: str | None) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if len(s) > 120:
        return False
    allowed = frozenset(".…\t\n\r ")
    return all(c in allowed for c in s)


def _is_micro_garbage_reply(text: str | None) -> bool:
    """Single-token fragments (e.g. one Russian inflected word) are not a real answer."""
    s = (text or "").strip()
    if len(s) < 4 or len(s) > 24:
        return False
    if any(c.isspace() for c in s):
        return False
    return all(c.isalnum() or c in "_-" for c in s)


def _degenerate_assistant_reply(text: str | None) -> bool:
    return _is_placeholder_only_reply(text) or _is_micro_garbage_reply(text)


def _proxy_ollama_chat_text_parts(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Non-stream /api/chat; returns separated text parts plus merged visible content."""
    _co = dict(getattr(chat_client, "_default_options", None) or {})
    if options_overlay:
        _co.update(options_overlay)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": dict(_co),
    }
    if think is not None:
        payload["think"] = think
    chat_fn = getattr(chat_client, "chat_api", None)
    if callable(chat_fn):
        data = chat_fn(payload)
        msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        out = _assistant_text_parts_from_ollama_message(msg if isinstance(msg, dict) else {})
        out["ollama_payload"] = data if isinstance(data, dict) else {}
        return out
    text = chat_client.chat(
        messages, model, stream=False, options=options_overlay if options_overlay else None, think=think
    )
    visible = (text or "").strip()
    return {
        "visible_content": visible,
        "reasoning_content": "",
        "final_content": visible,
        "ollama_payload": {},
    }


def _proxy_ollama_chat_text(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
) -> str:
    """Non-stream /api/chat; returns merged visible assistant text (thinking + content)."""
    return _proxy_ollama_chat_text_parts(
        chat_client,
        messages,
        model,
        think,
        options_overlay=options_overlay,
    )["visible_content"]


def _iter_proxy_ollama_chat_stream(
    chat_client: Any,
    messages: list[dict[str, Any]],
    model: str,
    think: bool | str | None,
    *,
    options_overlay: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Stream /api/chat; yield event tuples from ``iter_chat_api_stream_events``.

    Mirrors ``_proxy_ollama_chat_text`` but streaming.  Falls back to a single
    visible turn when the client has no streaming support.
    """
    _co = dict(getattr(chat_client, "_default_options", None) or {})
    if options_overlay:
        _co.update(options_overlay)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": dict(_co),
    }
    if think is not None:
        payload["think"] = think
    if tools:
        payload["tools"] = tools
    _tc_ollama = ollama_chat_tool_choice_payload_value(tool_choice)
    if _tc_ollama is not None:
        payload["tool_choice"] = _tc_ollama

    stream_fn = getattr(chat_client, "iter_chat_api_stream_events", None)
    if callable(stream_fn):
        yield from stream_fn(payload)
    else:
        chat_api_fn = getattr(chat_client, "chat_api", None)
        if callable(chat_api_fn):
            data = chat_api_fn(payload)
            msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            parts = _assistant_text_parts_from_ollama_message(msg if isinstance(msg, dict) else {})
            if parts["reasoning_content"]:
                yield ("thinking_delta", parts["reasoning_content"])
            if parts["final_content"]:
                yield ("content_delta", parts["final_content"])
            tc = msg.get("tool_calls") if isinstance(msg, dict) else None
            if isinstance(tc, list) and tc:
                yield ("tool_calls", tc)
            yield ("done", data if isinstance(data, dict) else {})
        else:
            parts = _proxy_ollama_chat_text_parts(
                chat_client, messages, model, think, options_overlay=options_overlay,
            )
            if parts["reasoning_content"]:
                yield ("thinking_delta", parts["reasoning_content"])
            if parts["final_content"]:
                yield ("content_delta", parts["final_content"])
            elif parts["visible_content"]:
                yield ("content_delta", parts["visible_content"])
            yield ("done", {})


def ollama_messages_have_images(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        images = msg.get("images")
        if isinstance(images, list) and len(images) > 0:
            return True
    return False


def vision_fallback_preferences(active_build: dict[str, Any] | None) -> tuple[str, ...]:
    raw: list[str] = []
    if active_build is not None:
        raw.append(str(active_build.get("vision_model") or "").strip())
    raw.append(os.getenv("LLM_PROXY_VISION_FALLBACK_MODEL", "").strip())
    raw.extend(
        (
            "minimax-m3:cloud",
            "kimi-k2.6:cloud",
            "gemini-3-flash-preview:cloud",
        )
    )
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


def resolved_ollama_chat_url(chat_client: Any) -> str | None:
    provider_id = str(getattr(chat_client, "_provider_id", "") or "").strip().lower()
    raw_url = getattr(chat_client, "_url", None)
    if isinstance(raw_url, str) and raw_url.strip():
        return raw_url.strip()
    if provider_id and provider_id != "ollama":
        return None
    try:
        from config import get_default_chat_url as _get_chat_url  # type: ignore[import-not-found]

        chat_url = str(_get_chat_url() or "").strip()
        if chat_url:
            return chat_url
    except Exception:
        return None
    return None
