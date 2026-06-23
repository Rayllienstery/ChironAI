"""Upstream JSON size budgeting for Ollama chat messages."""

from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT_UPSTREAM_JSON_CAP = 380_000
_MIN_UPSTREAM_JSON_CAP = 160_000
_MAX_UPSTREAM_JSON_CAP = 2_000_000
_UPSTREAM_JSON_CAP_ENV = "LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP"


def resolve_upstream_json_cap(
    input_budget: dict[str, Any] | None,
    *,
    env_var: str = _UPSTREAM_JSON_CAP_ENV,
    default_cap: int = _DEFAULT_UPSTREAM_JSON_CAP,
) -> int:
    """Resolve the JSON char cap for upstream message compaction."""
    try:
        cap_raw = os.getenv(env_var, str(default_cap)).strip()
        upstream_json_cap = int(cap_raw)
    except (TypeError, ValueError):
        upstream_json_cap = default_cap
    upstream_json_cap = max(_MIN_UPSTREAM_JSON_CAP, min(upstream_json_cap, _MAX_UPSTREAM_JSON_CAP))
    if input_budget is not None:
        upstream_json_cap = min(
            upstream_json_cap,
            int(input_budget.get("input_budget_json_chars") or upstream_json_cap),
        )
    return upstream_json_cap


def compact_upstream_messages_for_budget(
    messages: list[Any],
    input_budget: dict[str, Any] | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Compact upstream messages using env cap, optionally limited by input budget."""
    budget_json_chars = resolve_upstream_json_cap(input_budget)
    compacted_messages, compact_diag = _compact_upstream_messages_for_budget(
        messages,
        budget_json_chars=budget_json_chars,
    )
    if input_budget is not None:
        compact_diag["reserved_output_tokens"] = input_budget["reserved_output_tokens"]
        compact_diag["safety_margin_tokens"] = input_budget["safety_margin_tokens"]
        compact_diag["input_budget_tokens"] = input_budget["input_budget_tokens"]
    return compacted_messages, compact_diag


def _ollama_message_content_str(content: Any) -> str:
    """String form of an Ollama message ``content`` for logging / token estimates."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ""
    return str(content)


def _serialized_upstream_messages_chars(messages: list[Any]) -> int:
    try:
        return len(json.dumps(messages, ensure_ascii=False))
    except (TypeError, ValueError):
        run = 0
        for m in messages:
            if isinstance(m, dict):
                run += len(_ollama_message_content_str(m.get("content")))
                tc = m.get("tool_calls")
                if tc is not None:
                    try:
                        run += len(json.dumps(tc, ensure_ascii=False))
                    except (TypeError, ValueError):
                        run += len(str(tc))
            else:
                run += len(str(m))
        return run


def _truncate_old_tool_outputs_for_upstream_budget(
    messages: list[Any],
    *,
    budget_json_chars: int,
    per_message_ceiling: int = 12_000,
    preserve_tail_tool_roles: int = 24,
) -> tuple[list[Any], dict[str, Any]]:
    """Shorten oldest tool message bodies until JSON(serialized messages) fits the budget."""
    start_chars = _serialized_upstream_messages_chars(messages)
    diag: dict[str, Any] = {
        "original_upstream_json_chars": start_chars,
        "budget_json_chars": int(budget_json_chars),
    }
    if start_chars <= budget_json_chars:
        diag["compacted"] = False
        return messages, diag

    out: list[Any] = []
    for m in messages:
        out.append(dict(m) if isinstance(m, dict) else m)

    tool_indices = [
        i
        for i, m in enumerate(out)
        if isinstance(m, dict) and str(m.get("role") or "").strip().lower() == "tool"
    ]
    protected_tail = frozenset(tool_indices[-preserve_tail_tool_roles:])
    shortened_total = 0
    ceilings = (
        per_message_ceiling,
        max(4096, per_message_ceiling // 3),
        4096,
        2048,
        1024,
        512,
    )

    def _trim_once(ceiling: int) -> int:
        nonlocal shortened_total
        changed = 0
        for i in tool_indices:
            if i in protected_tail:
                continue
            m = out[i]
            if not isinstance(m, dict):
                continue
            raw_content = m.get("content")
            s = _ollama_message_content_str(raw_content)
            if len(s) <= ceiling:
                continue
            drop = len(s) - ceiling
            m["content"] = (
                f"{s[:ceiling].rstrip()}\n\n... [truncated {drop} chars for upstream budget]"
            )
            changed += 1
            shortened_total += 1
        return changed

    for ceil in ceilings:
        _trim_once(ceil)
        cur = _serialized_upstream_messages_chars(out)
        if cur <= budget_json_chars:
            diag["compacted"] = True
            diag["final_upstream_json_chars"] = cur
            diag["tool_messages_shortened_rounds"] = shortened_total
            diag["applied_ceiling"] = ceil
            return out, diag

    diag["compacted"] = True
    diag["still_over_budget_after_tool_trim"] = True
    diag["final_upstream_json_chars"] = _serialized_upstream_messages_chars(out)
    diag["tool_messages_shortened_rounds"] = shortened_total
    return out, diag


def _compact_upstream_messages_for_budget(
    messages: list[Any],
    *,
    budget_json_chars: int,
    preserve_tail_tool_roles: int = 12,
) -> tuple[list[Any], dict[str, Any]]:
    """Compact old chat/tool history until upstream JSON fits the input budget."""
    out, diag = _truncate_old_tool_outputs_for_upstream_budget(
        messages,
        budget_json_chars=budget_json_chars,
        per_message_ceiling=8_000,
        preserve_tail_tool_roles=preserve_tail_tool_roles,
    )
    if _serialized_upstream_messages_chars(out) <= budget_json_chars:
        return out, diag

    out = [dict(m) if isinstance(m, dict) else m for m in out]
    last_user_idx = -1
    for i in range(len(out) - 1, -1, -1):
        m = out[i]
        if isinstance(m, dict) and str(m.get("role") or "").strip().lower() == "user":
            last_user_idx = i
            break

    assistant_trimmed = 0
    tool_call_args_trimmed = 0
    message_summarized = 0
    for ceiling in (2048, 1024, 512, 256):
        for i, m in enumerate(out):
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").strip().lower()
            if role == "system" or i == last_user_idx:
                continue
            if role == "assistant":
                content = _ollama_message_content_str(m.get("content"))
                if len(content) > ceiling:
                    m["content"] = (
                        f"{content[:ceiling].rstrip()}\n\n... [truncated {len(content) - ceiling} chars for upstream budget]"
                    )
                    assistant_trimmed += 1
                tool_calls = m.get("tool_calls")
                if isinstance(tool_calls, list):
                    next_calls: list[Any] = []
                    for tc in tool_calls:
                        if not isinstance(tc, dict):
                            next_calls.append(tc)
                            continue
                        tco = dict(tc)
                        fn = tco.get("function") if isinstance(tco.get("function"), dict) else None
                        if isinstance(fn, dict):
                            fno = dict(fn)
                            args = fno.get("arguments")
                            if isinstance(args, str) and len(args) > ceiling:
                                fno["arguments"] = (
                                    f"{args[:ceiling].rstrip()}\n\n... [truncated {len(args) - ceiling} chars for upstream budget]"
                                )
                                tool_call_args_trimmed += 1
                            tco["function"] = fno
                        next_calls.append(tco)
                    m["tool_calls"] = next_calls
            elif role == "tool" and i != last_user_idx:
                content = _ollama_message_content_str(m.get("content"))
                if len(content) > ceiling:
                    m["content"] = (
                        f"{content[:ceiling].rstrip()}\n\n... [truncated {len(content) - ceiling} chars for upstream budget]"
                    )
                    message_summarized += 1
        if _serialized_upstream_messages_chars(out) <= budget_json_chars:
            break

    final_chars = _serialized_upstream_messages_chars(out)
    diag["compacted"] = bool(diag.get("compacted")) or final_chars < int(diag.get("original_upstream_json_chars") or final_chars)
    diag["final_upstream_json_chars"] = final_chars
    if assistant_trimmed:
        diag["assistant_messages_shortened_rounds"] = assistant_trimmed
    if tool_call_args_trimmed:
        diag["assistant_tool_call_arguments_shortened_rounds"] = tool_call_args_trimmed
    if message_summarized:
        diag["tool_messages_extra_shortened_rounds"] = message_summarized
    if final_chars > budget_json_chars:
        diag["still_over_budget_after_history_compaction"] = True
    return out, diag
