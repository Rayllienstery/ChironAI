"""Pure response and message-shaping helpers for /v1/chat/completions."""

from __future__ import annotations

from typing import Any


def reasoning_sse_delta(kind: str, data: Any, *, include_reasoning_content: bool) -> dict[str, Any]:
    if kind == "thinking_delta" and not include_reasoning_content:
        return {"reasoning_content": data}
    return {"content": data}


def stream_reasoning_guard_message(
    *,
    reasoning_text: str,
    final_text: str,
    tool_calls_count: int,
    limit_chars: int,
) -> str:
    if tool_calls_count > 0 or final_text.strip():
        return ""
    if len(reasoning_text) <= limit_chars:
        return ""
    return (
        "[Error: reasoning-only response guard triggered: model produced "
        f"{len(reasoning_text)} reasoning chars without final content or tool calls. "
        "Try disabling thinking or shortening the prompt.]"
    )


def record_reasoning_token_estimates(response: dict[str, Any], reasoning: str, final: str) -> None:
    response["reasoning_tokens_estimated"] = max(0, int(len(reasoning or "") / 4))
    response["final_tokens_estimated"] = max(0, int(len(final or "") / 4))


def with_initial_system_message(messages: list[dict[str, Any]], content: str) -> list[dict[str, Any]]:
    text = (content or "").strip()
    if not text:
        return messages
    out = list(messages)
    if out and isinstance(out[0], dict) and out[0].get("role") == "system":
        first = dict(out[0])
        existing = str(first.get("content") or "").strip()
        first["content"] = f"{existing}\n\n{text}" if existing else text
        out[0] = first
        return out
    return [{"role": "system", "content": text}, *out]


def final_or_compat_content(parts: dict[str, Any], *, include_reasoning_content: bool) -> str:
    if include_reasoning_content:
        return str(parts.get("visible_content") or "")
    return str(parts.get("final_content") or "")


def text_parts_from_openai_assistant_message(message: dict[str, Any]) -> dict[str, str]:
    reasoning = str(message.get("reasoning_content") or "").strip()
    final = str(message.get("content") or "").strip()
    visible = "\n\n".join(part for part in (reasoning, final) if part)
    return {
        "visible_content": visible,
        "reasoning_content": reasoning,
        "final_content": final,
    }


def tool_loop_limit_final_message(trace: dict[str, Any]) -> str:
    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    if req.get("tool_loop_limit_reached") is not True:
        return ""
    stats = req.get("tool_loop_stats") if isinstance(req.get("tool_loop_stats"), dict) else {}
    rounds = stats.get("rounds")
    dominant_tool = str(stats.get("dominant_tool") or "").strip()
    detail = f" after {rounds} tool rounds" if rounds else ""
    if dominant_tool:
        detail += f" ({dominant_tool})"
    return (
        f"[Error: max_agent_steps limit reached{detail}. "
        "The model requested another tool call after tools were disabled for this turn. "
        "The answer may be incomplete and the task may not be finished. "
        "Increase the build max_agent_steps limit, narrow the task, or continue in a new turn.]"
    )


def proxy_settings_optional_int(ps: dict[str, Any], key: str, lo: int, hi: int) -> int | None:
    if not isinstance(ps, dict):
        return None
    raw = ps.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n
