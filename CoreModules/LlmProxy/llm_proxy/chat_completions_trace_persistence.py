"""Proxy trace persistence helpers for chat completions."""

from __future__ import annotations

from typing import Any


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
    if extra_metadata:
        metadata.update(extra_metadata)
    return metadata
