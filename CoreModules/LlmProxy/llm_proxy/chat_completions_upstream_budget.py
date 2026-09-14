"""Upstream JSON size budgeting for Ollama chat messages."""

from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT_UPSTREAM_JSON_CAP = 380_000
_MIN_UPSTREAM_JSON_CAP = 160_000
_MAX_UPSTREAM_JSON_CAP = 4_194_304
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
        try:
            budget_chars = int(input_budget.get("input_budget_json_chars") or 0)
        except (TypeError, ValueError):
            budget_chars = 0
        if budget_chars > 0:
            # Model window is the authority: small ctx may shrink below the env
            # default, flash/smart 1M may raise it. Absolute max still applies.
            upstream_json_cap = max(1, min(budget_chars, _MAX_UPSTREAM_JSON_CAP))
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


def _message_role(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    return str(message.get("role") or "").strip().lower()


def _conversation_tail_start_index(messages: list[Any]) -> int:
    """Start of the live turn: last user, or last assistant when there is no user.

    Prefill/current-draft assistant messages after the last user must not be
    compacted — providers often echo that text back as the visible reply.
    """
    last_user = -1
    last_assistant = -1
    for i, message in enumerate(messages):
        role = _message_role(message)
        if role == "user":
            last_user = i
        elif role == "assistant":
            last_assistant = i
    if last_user >= 0:
        return last_user
    if last_assistant >= 0:
        return last_assistant
    return len(messages)


def _last_prefill_assistant_index(messages: list[Any]) -> int | None:
    """Last message is an assistant draft without tool_calls — keep it verbatim."""
    if not messages:
        return None
    idx = len(messages) - 1
    last = messages[idx]
    if _message_role(last) != "assistant" or not isinstance(last, dict):
        return None
    if last.get("tool_calls"):
        return None
    return idx


def _strip_images_except_index(messages: list[Any], keep_idx: int) -> int:
    """Drop image payloads from older turns so vision tokens do not blow the window."""
    dropped = 0
    for i, message in enumerate(messages):
        if i == keep_idx or not isinstance(message, dict):
            continue
        if message.get("images"):
            message.pop("images", None)
            dropped += 1
        content = message.get("content")
        if not isinstance(content, list):
            continue
        kept: list[Any] = []
        removed = False
        for part in content:
            if isinstance(part, dict) and str(part.get("type") or "").lower() in {
                "image",
                "image_url",
                "input_image",
            }:
                removed = True
                continue
            kept.append(part)
        if removed:
            message["content"] = kept
            dropped += 1
    return dropped


def _budget_truncated_text(text: str, ceiling: int) -> str:
    return f"{text[:ceiling].rstrip()}\n\n... [truncated {len(text) - ceiling} chars for upstream budget]"


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
    preserve_tail_tool_roles: int = 6,
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

    tool_indices = [i for i, m in enumerate(out) if _message_role(m) == "tool"]
    # Keep only the newest tool bodies. Older results in the *current* Hermes
    # turn are the usual 1M-token blow-up; protecting everything after last
    # user made compaction a no-op.
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
            m["content"] = _budget_truncated_text(s, ceiling)
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


def _trim_assistant_tool_calls(message: dict[str, Any], ceiling: int) -> int:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return 0
    trimmed = 0
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
                fno["arguments"] = _budget_truncated_text(args, ceiling)
                trimmed += 1
            tco["function"] = fno
        next_calls.append(tco)
    message["tool_calls"] = next_calls
    return trimmed


def _compact_upstream_messages_for_budget(
    messages: list[Any],
    *,
    budget_json_chars: int,
    preserve_tail_tool_roles: int = 6,
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
    tail_start = _conversation_tail_start_index(out)
    prefill_idx = _last_prefill_assistant_index(out)
    images_dropped = _strip_images_except_index(out, tail_start)
    if images_dropped:
        diag["images_dropped_from_older_messages"] = images_dropped

    assistant_trimmed = 0
    tool_call_args_trimmed = 0
    message_summarized = 0

    def _protected(i: int) -> bool:
        return i in (prefill_idx, tail_start)

    for ceiling in (8192, 4096, 2048):
        for i, m in enumerate(out):
            if not isinstance(m, dict) or _protected(i):
                continue
            if _message_role(m) != "assistant":
                continue
            content = _ollama_message_content_str(m.get("content"))
            if len(content) > ceiling:
                m["content"] = _budget_truncated_text(content, ceiling)
                assistant_trimmed += 1
            tool_call_args_trimmed += _trim_assistant_tool_calls(m, ceiling)
        if _serialized_upstream_messages_chars(out) <= budget_json_chars:
            break

    if _serialized_upstream_messages_chars(out) > budget_json_chars:
        tool_indices = [i for i, m in enumerate(out) if _message_role(m) == "tool"]
        keep_recent = frozenset(tool_indices[-2:])
        for ceiling in (2048, 1024, 512, 256):
            for i, m in enumerate(out):
                if not isinstance(m, dict) or i in keep_recent or _protected(i):
                    continue
                if _message_role(m) != "tool":
                    continue
                content = _ollama_message_content_str(m.get("content"))
                if len(content) > ceiling:
                    m["content"] = _budget_truncated_text(content, ceiling)
                    message_summarized += 1
            if _serialized_upstream_messages_chars(out) <= budget_json_chars:
                break

        if _serialized_upstream_messages_chars(out) > budget_json_chars:
            for ceiling in (8000, 4000, 2000, 1000):
                for i, m in enumerate(out):
                    if not isinstance(m, dict) or _protected(i):
                        continue
                    if _message_role(m) != "tool":
                        continue
                    content = _ollama_message_content_str(m.get("content"))
                    if len(content) > ceiling:
                        m["content"] = _budget_truncated_text(content, ceiling)
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
    if final_chars <= budget_json_chars:
        diag.pop("still_over_budget_after_tool_trim", None)
        diag.pop("still_over_budget_after_history_compaction", None)
    else:
        diag["still_over_budget_after_history_compaction"] = True
    return out, diag
