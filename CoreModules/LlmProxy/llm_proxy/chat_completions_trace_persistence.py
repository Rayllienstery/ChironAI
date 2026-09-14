"""Proxy trace persistence helpers for chat completions."""

from __future__ import annotations

from typing import Any

_URL_FETCH_STORE_CAP = 50


def _url_list_from_value(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for item in raw:
        text = str(item).strip() if item is not None else ""
        if not text:
            continue
        key = text.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(text)
        if len(urls) >= _URL_FETCH_STORE_CAP:
            break
    return urls


def _url_fetch_from_trace(trace_payload: dict[str, Any]) -> tuple[int, list[str]]:
    if not isinstance(trace_payload, dict):
        return 0, []
    request = trace_payload.get("request") if isinstance(trace_payload.get("request"), dict) else {}
    internet = trace_payload.get("internet") if isinstance(trace_payload.get("internet"), dict) else {}
    urls = _url_list_from_value(request.get("url_fetch_urls") or internet.get("url_fetch_urls"))
    count_raw = request.get("url_fetch_count")
    if count_raw is None:
        count_raw = internet.get("url_fetch_count")
    try:
        count = int(count_raw) if count_raw is not None else len(urls)
    except (TypeError, ValueError):
        count = len(urls)
    return max(count, 0), urls


def build_proxy_request_log_metadata(
    *,
    user_query: str,
    response_preview: str,
    trace_id: str,
    use_model: str,
    latency_ms_value: int,
    trace_payload: dict[str, Any],
    stream_value: bool,
    is_autocomplete: bool,
    requested_model: str,
    proxy_backend: str,
    include_rag_fields: bool,
    rag_context_data: Any,
    rag_timings: Any,
    include_token_fields: bool,
    prompt_tokens_value: int | None = None,
    completion_tokens_value: int | None = None,
    total_tokens_value: int | None = None,
    ollama_chat_stream: bool | None = None,
    sse_single_chunk: bool = False,
    extra_metadata: dict[str, Any] | None = None,
    trace_chain_id: str = "",
) -> dict[str, Any]:
    """Build the metadata dict stored with proxy request logs."""
    metadata: dict[str, Any] = {
        "user_query": user_query[:500],
        "response_preview": response_preview[:500],
        "trace_id": trace_id,
        "model": use_model,
        "latency_ms": latency_ms_value,
        "trace": trace_payload,
        "stream": bool(stream_value),
        "is_autocomplete": bool(is_autocomplete),
        "requested_model": requested_model,
        "proxy_backend": proxy_backend,
    }
    if trace_chain_id:
        metadata["trace_chain_id"] = trace_chain_id
    if include_rag_fields:
        metadata["rag_context"] = rag_context_data
        metadata["rag_steps"] = rag_timings
    if include_token_fields:
        metadata["prompt_tokens"] = prompt_tokens_value
        metadata["completion_tokens"] = completion_tokens_value
        metadata["total_tokens"] = total_tokens_value
    if ollama_chat_stream is not None:
        metadata["ollama_chat_stream"] = bool(ollama_chat_stream)
    if sse_single_chunk:
        metadata["sse_single_chunk"] = True
    url_fetch_count, url_fetch_urls = _url_fetch_from_trace(trace_payload)
    if url_fetch_urls:
        metadata["url_fetch_urls"] = url_fetch_urls
    if url_fetch_count:
        metadata["url_fetch_count"] = url_fetch_count
    if extra_metadata:
        metadata.update(extra_metadata)
    return metadata
