"""Pure response and message-shaping helpers for /v1/chat/completions."""

from __future__ import annotations

import re
from typing import Any

_REQUESTS_HTTP_ERROR_RE = re.compile(
    r"^(?P<status>\d{3})\s+.*?Error:\s*(?P<detail>.+?)\s+for url:\s*(?P<url>\S+)\s*$",
    re.IGNORECASE,
)
_OLLAMA_JSON_ERROR_RE = re.compile(r'"error"\s*:\s*"(?P<detail>(?:\\.|[^"\\])*)"', re.IGNORECASE)
_SERIALIZED_RESPONSE_NONE_RE = re.compile(r"['\"]response['\"]\s*:\s*None")
_STATUS_CODE_RE = re.compile(r"['\"]status_code['\"]\s*:\s*(?P<status>\d{3})")
_CONTENT_LENGTH_RE = re.compile(
    r"['\"]content-length['\"]\s*:\s*\[\s*['\"]Content-Length['\"]\s*,\s*['\"](?P<size>\d+)['\"]",
    re.IGNORECASE,
)
_WORKER_CALL_TIMEOUT_RE = re.compile(r"\bworker call timed out:\s*request\s+(?P<id>\d+)\b", re.IGNORECASE)
_UPSTREAM_ERROR_DETAIL_LIMIT = 500


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


def _exception_from_requests_error_text(text: str) -> Exception | None:
    match = _REQUESTS_HTTP_ERROR_RE.match(str(text or "").strip())
    if not match:
        return None
    err = Exception(str(text).strip())
    err.response = type(  # type: ignore[attr-defined]
        "UpstreamHttpResponse",
        (),
        {
            "status_code": int(match.group("status")),
            "reason": str(match.group("detail") or "").strip(),
            "url": str(match.group("url") or "").strip(),
        },
    )()
    return err


def _json_string_unescape(value: str) -> str:
    try:
        return str(value.encode("utf-8").decode("unicode_escape"))
    except Exception:
        return value


def _compact_upstream_error_detail(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    match = _OLLAMA_JSON_ERROR_RE.search(raw)
    if match:
        detail = _json_string_unescape(match.group("detail")).replace("\\'", "'").strip()
        if detail:
            return detail
    if len(raw) <= _UPSTREAM_ERROR_DETAIL_LIMIT:
        return raw
    return raw[:_UPSTREAM_ERROR_DETAIL_LIMIT].rstrip() + "... [truncated]"


def _status_code_from_error_text(text: str) -> str:
    match = _STATUS_CODE_RE.search(str(text or ""))
    return match.group("status") if match else ""


def _content_length_from_error_text(text: str) -> int | None:
    match = _CONTENT_LENGTH_RE.search(str(text or ""))
    if not match:
        return None
    try:
        return int(match.group("size"))
    except (TypeError, ValueError):
        return None


def _message_content_chars_from_trace(trace: dict[str, Any]) -> int | None:
    ollama = trace.get("ollama") if isinstance(trace.get("ollama"), dict) else {}
    messages = ollama.get("messages") if isinstance(ollama, dict) else None
    if not isinstance(messages, list):
        return None
    total = 0
    found = False
    for message in messages:
        if not isinstance(message, dict):
            continue
        try:
            total += int(message.get("content_length_chars") or 0)
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def _no_http_response_upstream_detail(exc_text: str, trace: dict[str, Any]) -> str:
    payload_size = _content_length_from_error_text(exc_text)
    message_chars = _message_content_chars_from_trace(trace)
    detail = "upstream Ollama request failed before receiving an HTTP response"
    diagnostics = []
    if payload_size:
        diagnostics.append(f"{payload_size}-byte request payload")
    if message_chars:
        diagnostics.append(f"{message_chars} message content chars")
    if diagnostics:
        detail = f"{detail} ({', '.join(diagnostics)}; large upstream context/tools are a strong suspect)"
    else:
        detail = f"{detail} (likely transport timeout/reset)"
    return detail


def _worker_timeout_upstream_detail(exc_text: str) -> str:
    match = _WORKER_CALL_TIMEOUT_RE.search(str(exc_text or ""))
    if not match:
        return ""
    return (
        "Ollama provider extension worker timed out before returning a chat response "
        f"(sandbox request {match.group('id')}); restart the ollama-provider worker from Extensions and retry"
    )


def upstream_chat_error_message(
    exc: Exception | str,
    trace: dict[str, Any],
    *,
    model: str = "",
) -> str:
    if isinstance(exc, str):
        parsed = _exception_from_requests_error_text(exc)
        exc = parsed if parsed is not None else RuntimeError(exc)
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    reason = str(getattr(response, "reason", "") or "").strip()
    url = str(getattr(response, "url", "") or "").strip()

    if status_code:
        status = str(status_code)
        if reason:
            status = f"{status} {reason}"
        parts = [f"upstream Ollama returned {status}"]
        if url:
            parts.append(f"for {url}")
    else:
        exc_text = str(exc)
        status = _status_code_from_error_text(exc_text)
        detail = _compact_upstream_error_detail(exc_text)
        if status:
            summary = f"upstream Ollama returned {status}"
            if detail:
                summary = f"{summary}: {detail}"
            parts = [summary]
        elif _SERIALIZED_RESPONSE_NONE_RE.search(exc_text):
            parts = [_no_http_response_upstream_detail(exc_text, trace)]
        elif worker_timeout := _worker_timeout_upstream_detail(exc_text):
            parts = [worker_timeout]
        else:
            parts = [f"upstream Ollama request failed: {detail or type(exc).__name__}"]

    if model:
        parts.append(f"while calling model {model}")

    req = trace.get("request") if isinstance(trace.get("request"), dict) else {}
    compaction = req.get("upstream_context_compaction") if isinstance(req.get("upstream_context_compaction"), dict) else {}
    if compaction.get("still_over_budget_after_tool_trim") is True:
        tokens = req.get("input_budget", {}).get("input_budget_tokens") if isinstance(req.get("input_budget"), dict) else None
        tool_count = req.get("tools_count_effective") or req.get("tools_count")
        detail = "The upstream request was still over budget after compaction"
        if tokens or tool_count:
            extras = []
            if tokens:
                extras.append(f"input budget {tokens} tokens")
            if tool_count:
                extras.append(f"{tool_count} tools")
            detail = f"{detail} ({', '.join(extras)})"
        parts.append(f"{detail}; retry in a fresh turn or reduce context/tools")

    return f"[Error: {' '.join(parts)}.]"


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
