"""OpenAI /v1/chat/completions handler — public entry and test-stable re-exports."""

from __future__ import annotations

from llm_proxy.chat_completions_gemini_native import (
    _gemini_tool_state_upsert_many,
    _interpolate_native_tools_for_gemini,
    _is_gemini_model_name,
    _preflight_native_tool_messages,
    _sanitize_outgoing_shell_tool_calls,
    _sse_tool_calls_payload,
    _tool_round_stats_since_last_user,
)
from llm_proxy.chat_completions_handler import (
    _apply_selected_rerank_model,
    _resolve_trace_chain_id,
    run_chat_completions,
)

__all__ = [
    "_apply_selected_rerank_model",
    "_gemini_tool_state_upsert_many",
    "_interpolate_native_tools_for_gemini",
    "_is_gemini_model_name",
    "_preflight_native_tool_messages",
    "_resolve_trace_chain_id",
    "_sanitize_outgoing_shell_tool_calls",
    "_sse_tool_calls_payload",
    "_tool_round_stats_since_last_user",
    "run_chat_completions",
]
