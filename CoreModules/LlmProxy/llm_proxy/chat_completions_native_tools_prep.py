"""Native OpenAI tools prep: tool-result analysis and agent step-limit policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm_proxy.chat_completions_gemini_native import _tool_round_stats_since_last_user
from llm_proxy.tool_helpers import _tool_result_looks_like_unintended_deletion

_TOOL_FAILURE_PHRASES = (
    "no edits were made",
    "no edits",
    "failed to receive tool input",
    "path not found",
    "can't edit file",
    "cannot edit file",
    "can't create file",
    "cannot create file",
    "parent directory doesn't exist",
    "parent directory does not exist",
    "file not found",
    "unknown variant",
)


def messages_have_tool_result(messages: list[Any]) -> bool:
    return any(isinstance(m, dict) and m.get("role") == "tool" for m in messages)


def last_tool_message_content(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "tool":
            return str(
                message.get("content")
                or message.get("output")
                or message.get("result")
                or message.get("text")
                or ""
            )
    return ""


def analyze_tool_result_failure(last_tool_content: str) -> bool:
    """Return True when the latest tool payload looks like a failed tool round."""
    lowered = last_tool_content.lower()
    if any(phrase in lowered for phrase in _TOOL_FAILURE_PHRASES):
        return True

    tool_ok_flag: bool | None = None
    tool_exit_code: int | None = None
    tool_error_text = ""
    try:
        parsed = json.loads(last_tool_content) if last_tool_content.strip().startswith(("{", "[")) else None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("ok"), bool):
                tool_ok_flag = bool(parsed.get("ok"))
            meta = parsed.get("metadata")
            if isinstance(meta, dict):
                exit_code = meta.get("exit_code")
                if isinstance(exit_code, (int, float)):
                    tool_exit_code = int(exit_code)
                stderr = meta.get("stderr")
                if isinstance(stderr, str) and stderr.strip():
                    tool_error_text = stderr.strip().lower()
            err = parsed.get("error")
            if isinstance(err, str) and err.strip():
                tool_error_text = (tool_error_text + "\n" + err.strip().lower()).strip()
    except Exception:  # safe: tool result metadata parse best-effort
        pass

    if tool_ok_flag is False:
        return True
    if tool_exit_code is not None and tool_exit_code != 0:
        return True
    if tool_error_text:
        return True
    return _tool_result_looks_like_unintended_deletion(last_tool_content)


def compute_post_tool_success_turn(
    messages: list[Any],
    *,
    has_tool_result: bool,
    tool_result_indicates_failure: bool,
) -> bool:
    """True when the latest message is a successful tool result with no newer user turn."""
    last_message = messages[-1] if messages else None
    last_role = last_message.get("role") if isinstance(last_message, dict) else None
    last_tool_idx = -1
    last_user_idx = -1
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if last_tool_idx < 0 and role == "tool":
            last_tool_idx = index
        if role == "user" and last_user_idx < 0:
            last_user_idx = index
        if last_tool_idx >= 0 and last_user_idx >= 0:
            break
    return bool(
        last_role == "tool"
        and has_tool_result
        and not tool_result_indicates_failure
        and (last_user_idx < 0 or last_user_idx < last_tool_idx)
    )


@dataclass(frozen=True)
class NativeToolsPolicy:
    tools: list[Any]
    tool_choice_effective: Any
    use_native_tools: bool
    tool_loop_stats: dict[str, Any] | None
    tool_loop_limit_reached: bool


def resolve_native_tools_policy(
    messages: list[Any],
    tools: list[Any],
    tool_choice_effective: Any,
    *,
    effective_max_agent_steps: int | None,
) -> NativeToolsPolicy:
    """Apply agent step limits and decide whether native tool calls stay enabled."""
    use_native_tools = bool(tools) and tool_choice_effective != "none"
    tool_loop_stats: dict[str, Any] | None = None
    if use_native_tools:
        tool_loop_stats = _tool_round_stats_since_last_user(messages)
    tool_loop_limit_reached = bool(
        use_native_tools
        and effective_max_agent_steps is not None
        and tool_loop_stats is not None
        and int(tool_loop_stats.get("rounds") or 0) >= effective_max_agent_steps
    )
    resolved_tools = list(tools)
    resolved_choice = tool_choice_effective
    resolved_use_native = use_native_tools
    if tool_loop_limit_reached:
        resolved_tools = []
        resolved_choice = "none"
        resolved_use_native = False
    return NativeToolsPolicy(
        tools=resolved_tools,
        tool_choice_effective=resolved_choice,
        use_native_tools=resolved_use_native,
        tool_loop_stats=tool_loop_stats,
        tool_loop_limit_reached=tool_loop_limit_reached,
    )


def analyze_tool_turn_state(messages: list[Any]) -> tuple[bool, str, bool, bool]:
    """Return has_tool_result, last_tool_content, tool_result_indicates_failure, post_tool_success_turn."""
    has_tool_result = messages_have_tool_result(messages)
    last_tool_content = last_tool_message_content(messages)
    tool_result_indicates_failure = analyze_tool_result_failure(last_tool_content)
    post_tool_success_turn = compute_post_tool_success_turn(
        messages,
        has_tool_result=has_tool_result,
        tool_result_indicates_failure=tool_result_indicates_failure,
    )
    return has_tool_result, last_tool_content, tool_result_indicates_failure, post_tool_success_turn
