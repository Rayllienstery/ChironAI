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
from llm_proxy.chat_completions_handler import run_chat_completions
from llm_proxy.chat_completions_handler_helpers import (
    apply_selected_rerank_model as _apply_selected_rerank_model,
)
from llm_proxy.chat_completions_request_parsing import (
    non_empty_str as _non_empty_str,
)
from llm_proxy.chat_completions_request_parsing import (
    positive_int_env as _positive_int_env,
)
from llm_proxy.chat_completions_request_parsing import (
    resolve_trace_chain_id as _resolve_trace_chain_id,
)
from llm_proxy.chat_completions_request_parsing import (
    truthy_body_flag as _truthy_body_flag,
)

__all__ = [
    "_apply_selected_rerank_model",
    "_gemini_tool_state_upsert_many",
    "_interpolate_native_tools_for_gemini",
    "_is_gemini_model_name",
    "_non_empty_str",
    "_positive_int_env",
    "_preflight_native_tool_messages",
    "_resolve_trace_chain_id",
    "_sanitize_outgoing_shell_tool_calls",
    "_sse_tool_calls_payload",
    "_tool_round_stats_since_last_user",
    "_truthy_body_flag",
    "run_chat_completions",
]
