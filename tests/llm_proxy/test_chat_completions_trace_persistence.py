from __future__ import annotations

from llm_proxy.chat_completions_trace_persistence import build_proxy_request_log_metadata


def test_build_proxy_request_log_metadata_includes_optional_fields() -> None:
    metadata = build_proxy_request_log_metadata(
        user_query="hello world",
        response_preview="hi",
        trace_id="trace-abc",
        use_model="llama3",
        latency_ms_value=42,
        trace_payload={"trace_id": "trace-abc"},
        stream_value=True,
        is_autocomplete=False,
        requested_model="build-1",
        proxy_backend="direct",
        include_rag_fields=True,
        rag_context_data={"chunks": 1},
        rag_timings={"search": 10},
        include_token_fields=True,
        prompt_tokens_value=5,
        completion_tokens_value=7,
        total_tokens_value=12,
        ollama_chat_stream=True,
        sse_single_chunk=True,
        extra_metadata={"finish_reason": "stop"},
    )
    assert metadata["trace_id"] == "trace-abc"
    assert metadata["rag_context"] == {"chunks": 1}
    assert metadata["prompt_tokens"] == 5
    assert metadata["ollama_chat_stream"] is True
    assert metadata["sse_single_chunk"] is True
    assert metadata["finish_reason"] == "stop"
