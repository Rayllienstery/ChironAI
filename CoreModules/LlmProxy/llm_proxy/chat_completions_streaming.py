"""OpenAI ``chat.completion.chunk`` SSE formatting and Ollama stream bridging."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from llm_proxy.chat_completions_request_parsing import positive_int_env
from llm_proxy.chat_completions_response_helpers import (
    reasoning_sse_delta,
    stream_reasoning_guard_message,
    upstream_chat_error_message,
)

DEFAULT_REASONING_ONLY_GUARD_CHARS = 512_000

SSE_RESPONSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
SSE_MIMETYPE = "text/event-stream"
SSE_DONE_LINE = "data: [DONE]\n\n"


def stream_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def openai_chat_completion_chunk(
    completion_id: str,
    model: str,
    *,
    delta: dict[str, Any],
    finish_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if extra:
        payload.update(extra)
    return f"data: {json.dumps(payload)}\n\n"


def context_window_tokens_from_trace(trace: dict[str, Any] | None) -> int | None:
    req = trace.get("request") if isinstance(trace, dict) else None
    if not isinstance(req, dict):
        return None
    try:
        n = int(req.get("effective_num_ctx") or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return n
    budget = req.get("input_budget")
    if isinstance(budget, dict):
        try:
            n = int(budget.get("num_ctx") or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return n
    return None


def upstream_context_tokens_from_trace(trace: dict[str, Any] | None) -> int | None:
    req = trace.get("request") if isinstance(trace, dict) else None
    if not isinstance(req, dict):
        return None
    try:
        n = int(req.get("upstream_num_ctx") or 0)
    except (TypeError, ValueError):
        n = 0
    return n if n > 0 else None


def format_context_window_percent(percent: float) -> str | None:
    if percent != percent or percent < 0:  # NaN or negative
        return None
    if 0 < percent < 0.5:
        return "<1%"
    return f"{int(round(percent))}%"


def format_owui_usage_status(
    *,
    completion_tokens: int,
    prompt_tokens: int = 0,
    num_ctx: int | None = None,
    upstream_num_ctx: int | None = None,
) -> str:
    """Open WebUI / CoreUI live chips: ``6982 tok · 11%`` (context-window fill)."""
    tok = max(0, int(completion_tokens))
    label = f"{tok} tok"
    used = max(0, int(prompt_tokens)) + tok
    window = int(num_ctx or 0)
    upstream = int(upstream_num_ctx or 0)
    percents: list[str] = []
    if upstream > 0:
        pct = format_context_window_percent((used / upstream) * 100)
        if pct:
            percents.append(pct)
    if window > 0 and window != upstream:
        pct = format_context_window_percent((used / window) * 100)
        if pct:
            percents.append(pct)
    if not percents:
        return label
    return f"{label} · {' | '.join(percents)}"


def owui_usage_status_event(description: str, *, done: bool = False) -> dict[str, Any]:
    """Open WebUI middleware lifts ``event`` on an SSE chunk into the status line."""
    return {
        "type": "status",
        "data": {
            "description": (description or "").strip(),
            "done": bool(done),
            "hidden": False,
            "action": "chiron_ctx",
        },
    }


def sse_role_assistant_chunk(completion_id: str, model: str) -> str:
    return openai_chat_completion_chunk(completion_id, model, delta={"role": "assistant"})


def sse_content_chunk(completion_id: str, model: str, content: str) -> str:
    return openai_chat_completion_chunk(completion_id, model, delta={"content": content})


def sse_finish_chunk(completion_id: str, model: str, finish_reason: str) -> str:
    return openai_chat_completion_chunk(completion_id, model, delta={}, finish_reason=finish_reason)


def approx_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def reasoning_guard_limit_from_env() -> int:
    return positive_int_env(
        "LLM_PROXY_REASONING_ONLY_GUARD_CHARS",
        DEFAULT_REASONING_ONLY_GUARD_CHARS,
    )


@dataclass
class StreamContentAccumulator:
    visible_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    final_parts: list[str] = field(default_factory=list)
    tool_calls_raw: list[Any] = field(default_factory=list)
    ollama_done_reason: Any = None
    ollama_done_payload: dict[str, Any] | None = None
    reasoning_guard_triggered: bool = False

    @property
    def visible_content(self) -> str:
        return "".join(self.visible_parts)

    @property
    def reasoning_content(self) -> str:
        return "".join(self.reasoning_parts)

    @property
    def final_content(self) -> str:
        return "".join(self.final_parts)


def iter_sse_from_ollama_stream_events(
    events: Iterator[tuple[str, Any]],
    *,
    completion_id: str,
    client_visible_model: str,
    include_reasoning_content: bool,
    accumulator: StreamContentAccumulator,
    reasoning_guard_limit_chars: int,
    on_reasoning_guard: Callable[[], None] | None = None,
    upstream_model: str = "",
    trace: dict[str, Any] | None = None,
    on_visible_progress: Callable[[str], None] | None = None,
    extra_chunk_fields: Callable[[str], dict[str, Any]] | None = None,
) -> Iterator[str]:
    """Map Ollama stream events to OpenAI-style SSE chunk lines.

    Reasoning is streamed through to completion. The char limit only sets a
    trace flag after upstream `done`; it never injects chat errors.
    """
    for kind, data in events:
        if kind in ("thinking_delta", "content_delta") and data:
            text_part = str(data)
            accumulator.visible_parts.append(text_part)
            if kind == "thinking_delta":
                accumulator.reasoning_parts.append(text_part)
            else:
                accumulator.final_parts.append(text_part)
            delta = reasoning_sse_delta(
                kind,
                data,
                include_reasoning_content=include_reasoning_content,
            )
            extra = extra_chunk_fields(accumulator.visible_content) if extra_chunk_fields is not None else None
            yield openai_chat_completion_chunk(
                completion_id,
                client_visible_model,
                delta=delta,
                extra=extra or None,
            )
            if on_visible_progress is not None:
                on_visible_progress(accumulator.visible_content)
        elif kind == "tool_calls" and data:
            accumulator.tool_calls_raw = data if isinstance(data, list) else []
        elif kind == "done" and isinstance(data, dict):
            accumulator.ollama_done_payload = data
            accumulator.ollama_done_reason = data.get("done_reason")
            guard_error = stream_reasoning_guard_message(
                reasoning_text=accumulator.reasoning_content,
                final_text=accumulator.final_content,
                tool_calls_count=len(accumulator.tool_calls_raw),
                limit_chars=reasoning_guard_limit_chars,
            )
            if guard_error:
                accumulator.reasoning_guard_triggered = True
                if on_reasoning_guard is not None:
                    on_reasoning_guard()
        elif kind == "error":
            err_source: Exception | str
            err_source = data if isinstance(data, BaseException) else str(data)
            err_text = upstream_chat_error_message(
                err_source,
                trace if isinstance(trace, dict) else {},
                model=upstream_model,
            )
            accumulator.visible_parts.append(err_text)
            accumulator.final_parts.append(err_text)
            yield sse_content_chunk(completion_id, client_visible_model, err_text)
            if on_visible_progress is not None:
                on_visible_progress(accumulator.visible_content)
            return


def iter_sse_tool_limit_response(completion_id: str, model: str, content: str) -> Iterator[str]:
    yield sse_role_assistant_chunk(completion_id, model)
    yield sse_content_chunk(completion_id, model, content)
    yield sse_finish_chunk(completion_id, model, "stop")
    yield SSE_DONE_LINE


def iter_sse_plain_content_response(
    completion_id: str,
    model: str,
    content: str,
    *,
    finish_reason: str = "stop",
) -> Iterator[str]:
    yield sse_role_assistant_chunk(completion_id, model)
    yield sse_content_chunk(completion_id, model, content)
    yield sse_finish_chunk(completion_id, model, finish_reason)
    yield SSE_DONE_LINE


def iter_sse_tool_calls_response(
    completion_id: str,
    model: str,
    tool_calls_delta: list[dict[str, Any]],
) -> Iterator[str]:
    yield sse_role_assistant_chunk(completion_id, model)
    yield openai_chat_completion_chunk(
        completion_id,
        model,
        delta={"tool_calls": tool_calls_delta},
    )
    yield sse_finish_chunk(completion_id, model, "tool_calls")
    yield SSE_DONE_LINE


def iter_sse_single_shot_assistant(
    completion_id: str,
    model: str,
    *,
    content: str,
    reasoning_content: str,
    tool_calls_payload: list[dict[str, Any]] | None,
    finish_reason: str,
    include_reasoning_content: bool,
) -> Iterator[str]:
    yield sse_role_assistant_chunk(completion_id, model)
    if reasoning_content and not include_reasoning_content:
        yield openai_chat_completion_chunk(
            completion_id,
            model,
            delta={"reasoning_content": reasoning_content},
        )
    if content:
        yield sse_content_chunk(completion_id, model, content)
    if tool_calls_payload:
        yield openai_chat_completion_chunk(
            completion_id,
            model,
            delta={"tool_calls": tool_calls_payload},
        )
    yield sse_finish_chunk(completion_id, model, finish_reason)
    yield SSE_DONE_LINE


def iter_sse_finish_with_done(completion_id: str, model: str, finish_reason: str) -> Iterator[str]:
    """Emit finish chunk and ``[DONE]``; retry with ``stop`` if the client disconnects mid-yield."""
    try:
        yield sse_finish_chunk(completion_id, model, finish_reason)
        yield SSE_DONE_LINE
    except Exception:
        try:
            yield sse_finish_chunk(completion_id, model, "stop")
            yield SSE_DONE_LINE
        except Exception:  # safe: client disconnect during SSE finish; ignore
            pass
