"""Inline closures extracted from chat_completions_handler for testability and size reduction."""

from __future__ import annotations

import logging
from typing import Any

from api.http.proxy_trace import set_response_artifacts
from llm_proxy.chat_completions_trace_persistence import (
    build_proxy_request_log_metadata,
)

_RAG_LOG = logging.getLogger("llm_proxy")


def build_ollama_options_overlay(
    build_extra_options: dict[str, Any],
    chat_max_tokens: int | None,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = {**build_extra_options}
    if chat_max_tokens is not None:
        build_np = build_extra_options.get("num_predict")
        try:
            build_np_int = int(build_np)
        except (TypeError, ValueError):
            build_np_int = 0
        merged["num_predict"] = min(chat_max_tokens, build_np_int) if build_np_int > 0 else chat_max_tokens
    return merged if merged else None


def make_publish_trace(w: Any, private_build: bool):
    def publish_trace(tr: dict[str, Any]) -> None:
        if private_build:
            w.set_current_trace(None)
        else:
            w.set_current_trace(tr)

    return publish_trace


def make_publish_response_artifacts(trace: dict[str, Any], private_build: bool):
    def publish_response_artifacts(
        *,
        visible_content: str,
        reasoning_content: str = "",
        final_content: str = "",
    ) -> None:
        if private_build:
            return
        req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
        set_response_artifacts(
            trace_id=str(trace.get("trace_id") or "").strip() or None,
            client_request_id=str(req.get("client_request_id") or "").strip() or None,
            visible_content=visible_content,
            reasoning_content=reasoning_content,
            final_content=final_content,
        )

    return publish_response_artifacts


def proxy_backend_tag(*, is_autocomplete: bool, dumb_build_pipeline: bool) -> str:
    if is_autocomplete:
        return "autocomplete"
    if dumb_build_pipeline:
        return "rag_fusion"
    return "direct"


def make_persist_proxy_request_log(
    w: Any,
    *,
    private_build: bool,
    user_query: str,
    trace_id: str,
    trace_chain_id: str,
    is_autocomplete: bool,
    requested_model: str,
    dumb_build_pipeline: bool,
    rag_context_data: list[Any],
    rag_timings: list[Any],
    use_model_ref: list[str],
):
    _backend_tag = proxy_backend_tag(
        is_autocomplete=is_autocomplete,
        dumb_build_pipeline=dumb_build_pipeline,
    )

    def persist_proxy_request_log(
        *,
        message: str,
        response_preview: str,
        latency_ms_value: int,
        trace_payload: dict[str, Any],
        stream_value: bool,
        include_rag_fields: bool,
        include_token_fields: bool,
        prompt_tokens_value: int | None = None,
        completion_tokens_value: int | None = None,
        total_tokens_value: int | None = None,
        ollama_chat_stream: bool | None = None,
        sse_single_chunk: bool = False,
        extra_metadata: dict[str, Any] | None = None,
        warn_label: str,
    ) -> None:
        if private_build:
            return
        try:
            session_manager = w.get_session_manager()
            session_manager.get_or_create_session("proxy")
            logs_repo = w.get_logs_repository()
            metadata = build_proxy_request_log_metadata(
                user_query=user_query,
                response_preview=response_preview,
                trace_id=trace_id,
                use_model=use_model_ref[0],
                latency_ms_value=latency_ms_value,
                trace_payload=trace_payload,
                stream_value=stream_value,
                is_autocomplete=is_autocomplete,
                requested_model=requested_model,
                proxy_backend=_backend_tag,
                include_rag_fields=include_rag_fields,
                rag_context_data=rag_context_data[0],
                rag_timings=rag_timings[0],
                include_token_fields=include_token_fields,
                prompt_tokens_value=prompt_tokens_value,
                completion_tokens_value=completion_tokens_value,
                total_tokens_value=total_tokens_value,
                ollama_chat_stream=ollama_chat_stream,
                sse_single_chunk=sse_single_chunk,
                extra_metadata=extra_metadata,
                trace_chain_id=trace_chain_id,
            )
            logs_repo.upsert_proxy_journal_log(
                message=message,
                metadata=metadata,
                trace_chain_id=trace_chain_id,
            )
        except Exception as e:
            _RAG_LOG.warning("Failed to log proxy %s request to database: %s", warn_label, e)

    return persist_proxy_request_log
