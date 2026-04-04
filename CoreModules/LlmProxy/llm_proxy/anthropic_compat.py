"""
Anthropic Messages API <-> OpenAI chat completions (request/response/SSE).

Used by LlmProxy and ClawCode so Claude Code (ANTHROPIC_BASE_URL) can share the same
RAG/agent stack as OpenAI-compatible clients.

Known limitations:
- Rare content block types (images, PDFs, citations) are not fully mapped; text and
  tool_use / tool_result are supported for typical agent flows.
- Streaming tool arguments are emitted in one input_json_delta when OpenAI sends full
  tool_calls in a single chunk (matches this proxy's synthesized SSE).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterator

# Anthropic API version clients send; we accept any non-empty value.
ANTHROPIC_VERSION_HEADER = "anthropic-version"


def _new_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


def _blocks_to_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and isinstance(b.get("text"), str):
            parts.append(b["text"])
    return "".join(parts)


def _anthropic_system_to_openai_messages(system: Any) -> list[dict[str, Any]]:
    if system is None or system == "":
        return []
    if isinstance(system, str):
        return [{"role": "system", "content": system.strip()}] if system.strip() else []
    if isinstance(system, list):
        texts: list[str] = []
        for b in system:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                texts.append(b["text"])
        joined = "\n\n".join(texts).strip()
        return [{"role": "system", "content": joined}] if joined else []
    return []


def _anthropic_user_assistant_content_to_openai(
    role: str, content: Any
) -> tuple[str | None, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """Returns (plain_content, openai_content_parts, tool_calls) for assistant."""
    if content is None:
        return None, None, None
    if isinstance(content, str):
        return content, None, None
    if not isinstance(content, list):
        return str(content), None, None

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
        elif bt == "tool_use":
            tid = block.get("id") or f"toolu_{uuid.uuid4().hex[:20]}"
            name = block.get("name") or ""
            inp = block.get("input")
            if isinstance(inp, dict):
                args = json.dumps(inp, ensure_ascii=False)
            elif isinstance(inp, str):
                args = inp
            else:
                args = json.dumps(inp if inp is not None else {}, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": str(tid),
                    "type": "function",
                    "function": {"name": str(name), "arguments": args},
                }
            )
        elif bt == "tool_result":
            # Belongs in user turn as OpenAI "tool" messages — handled by caller
            pass

    if role == "assistant":
        tc = tool_calls if tool_calls else None
        txt = "".join(text_parts)
        if tc and not txt.strip():
            return None, None, tc
        if tc and txt.strip():
            return txt, None, tc
        return (txt if txt else None), None, None

    # user: tool_result blocks → caller splits into separate messages
    return None, None, None


def _flatten_anthropic_messages_to_openai(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role == "user":
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
                continue
            if isinstance(content, list):
                text_buf: list[str] = []

                def flush_text() -> None:
                    joined = "".join(text_buf).strip()
                    text_buf.clear()
                    if joined:
                        out.append({"role": "user", "content": joined})

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    bt = block.get("type")
                    if bt == "text" and isinstance(block.get("text"), str):
                        text_buf.append(block["text"])
                    elif bt == "tool_result":
                        flush_text()
                        tid = block.get("tool_use_id") or ""
                        tr_content = block.get("content")
                        if isinstance(tr_content, list):
                            tr_content = _blocks_to_text(
                                [x for x in tr_content if isinstance(x, dict)]
                            )
                        elif tr_content is None:
                            tr_content = ""
                        else:
                            tr_content = str(tr_content)
                        out.append(
                            {"role": "tool", "tool_call_id": str(tid), "content": tr_content}
                        )
                flush_text()
                continue
            out.append({"role": "user", "content": str(content)})
        elif role == "assistant":
            plain, _, tool_calls = _anthropic_user_assistant_content_to_openai("assistant", content)
            msg: dict[str, Any] = {"role": "assistant"}
            if plain:
                msg["content"] = plain
            else:
                msg["content"] = None
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:
            # Pass through system/developer if present (unusual in Anthropic messages array)
            if role in ("system", "developer"):
                c = content if isinstance(content, str) else str(content)
                out.append({"role": str(role), "content": c})
    return out


def anthropic_tools_to_openai(tools: Any) -> list[dict[str, Any]] | None:
    if not isinstance(tools, list) or not tools:
        return None
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not name:
            continue
        desc = t.get("description") or ""
        schema = t.get("input_schema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": str(name),
                    "description": str(desc),
                    "parameters": schema,
                },
            }
        )
    return out or None


def anthropic_tool_choice_to_openai(tc: Any) -> Any:
    if tc is None:
        return None
    if isinstance(tc, dict):
        t = tc.get("type")
        if t == "auto":
            return "auto"
        if t == "any":
            return "required"
        if t == "tool" and isinstance(tc.get("name"), str):
            return {"type": "function", "function": {"name": tc["name"]}}
    return tc


def anthropic_messages_request_to_openai_body(body: dict[str, Any]) -> dict[str, Any]:
    """Map POST /v1/messages JSON to OpenAI chat/completions-shaped dict."""
    out: dict[str, Any] = {
        "model": body.get("model") or "",
        "stream": bool(body.get("stream", False)),
    }
    if "max_tokens" in body:
        out["max_tokens"] = body["max_tokens"]
    if "temperature" in body:
        out["temperature"] = body["temperature"]
    if "top_p" in body:
        out["top_p"] = body["top_p"]
    if "top_k" in body:
        out["top_k"] = body["top_k"]
    if "stop_sequences" in body and isinstance(body["stop_sequences"], list):
        out["stop"] = body["stop_sequences"]
    if "metadata" in body:
        out["metadata"] = body["metadata"]

    msgs: list[dict[str, Any]] = []
    msgs.extend(_anthropic_system_to_openai_messages(body.get("system")))
    raw_messages = body.get("messages")
    if isinstance(raw_messages, list):
        msgs.extend(_flatten_anthropic_messages_to_openai(raw_messages))
    out["messages"] = msgs

    ot = anthropic_tools_to_openai(body.get("tools"))
    if ot:
        out["tools"] = ot
    otc = anthropic_tool_choice_to_openai(body.get("tool_choice"))
    if otc is not None:
        out["tool_choice"] = otc

    return out


def _openai_finish_to_anthropic_stop_reason(finish: str | None) -> str:
    if finish == "tool_calls":
        return "tool_use"
    if finish in ("length", "content_filter"):
        return "max_tokens"
    return "end_turn"


def openai_chat_completion_to_anthropic_message(
    openai_resp: dict[str, Any],
) -> dict[str, Any]:
    """Convert OpenAI chat.completion JSON to Anthropic message JSON."""
    msg_id = _new_msg_id()
    model = str(openai_resp.get("model") or "")
    choices = openai_resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": ""}],
            "model": model,
            "stop_reason": "error",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    ch0 = choices[0] if isinstance(choices[0], dict) else {}
    message = ch0.get("message") if isinstance(ch0.get("message"), dict) else {}
    finish = ch0.get("finish_reason")
    finish_s = str(finish) if finish is not None else "stop"

    content_blocks: list[dict[str, Any]] = []
    c = message.get("content")
    if isinstance(c, str) and c.strip():
        content_blocks.append({"type": "text", "text": c})
    elif isinstance(c, list):
        for block in c:
            if isinstance(block, dict) and block.get("type") == "text":
                content_blocks.append(block)
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                inp = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                inp = {"_raw": raw_args}
            if not isinstance(inp, dict):
                inp = {"value": inp}
            tid = tc.get("id") or f"toolu_{uuid.uuid4().hex[:20]}"
            content_blocks.append(
                {"type": "tool_use", "id": str(tid), "name": str(name), "input": inp}
            )

    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    usage_in = 0
    usage_out = 0
    u = openai_resp.get("usage")
    if isinstance(u, dict):
        usage_in = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
        usage_out = int(u.get("completion_tokens") or u.get("output_tokens") or 0)

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": _openai_finish_to_anthropic_stop_reason(finish_s),
        "stop_sequence": None,
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
    }


def anthropic_models_list_payload(model_ids: list[str]) -> dict[str, Any]:
    """Anthropic GET /v1/models shaped response."""
    data: list[dict[str, Any]] = []
    for mid in model_ids:
        if not mid:
            continue
        data.append(
            {
                "type": "model",
                "id": mid,
                "display_name": mid,
                "created_at": "1970-01-01T00:00:00Z",
            }
        )
    first_id = data[0]["id"] if data else ""
    return {"data": data, "first_id": first_id, "has_more": False}


def _sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def iter_anthropic_sse_from_openai_sse_lines(
    lines: Iterator[str],
    *,
    default_model: str,
) -> Iterator[str]:
    """
    Consume OpenAI-style SSE lines (``data: {...}`` / ``data: [DONE]``) and emit Anthropic SSE.

    Handles the common patterns produced by this repo's proxy: role chunk, single content
    or tool_calls chunk, final chunk with finish_reason.
    """
    msg_id = _new_msg_id()
    model = default_model
    started = False
    text_block_open = False
    tool_block_open = False
    tool_index = 0
    pending_tool: dict[str, Any] | None = None
    last_finish: str | None = None
    out_tokens_est = 0

    data_line_re = re.compile(r"^data:\s*(.*)$")

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        m = data_line_re.match(line)
        if not m:
            continue
        payload_s = m.group(1).strip()
        if payload_s == "[DONE]":
            if not started:
                yield _sse_event(
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": msg_id,
                            "type": "message",
                            "role": "assistant",
                            "content": [],
                            "model": model,
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        },
                    },
                )
            if text_block_open:
                yield _sse_event(
                    "content_block_stop", {"type": "content_block_stop", "index": 0}
                )
                text_block_open = False
            if tool_block_open and pending_tool:
                yield _sse_event(
                    "content_block_stop", {"type": "content_block_stop", "index": tool_index}
                )
                tool_block_open = False
            sr = _openai_finish_to_anthropic_stop_reason(last_finish or "stop")
            yield _sse_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": sr, "stop_sequence": None},
                    "usage": {"output_tokens": max(1, out_tokens_est)},
                },
            )
            yield _sse_event("message_stop", {"type": "message_stop"})
            break

        try:
            chunk = json.loads(payload_s)
        except json.JSONDecodeError:
            continue

        if chunk.get("model"):
            model = str(chunk["model"])

        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        c0 = choices[0] if isinstance(choices[0], dict) else {}
        delta = c0.get("delta") if isinstance(c0.get("delta"), dict) else {}
        finish = c0.get("finish_reason")

        if not started and (delta.get("role") == "assistant" or delta.get("content") or delta.get("tool_calls")):
            started = True
            yield _sse_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": msg_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": model,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 1},
                    },
                },
            )

        if delta.get("tool_calls"):
            tcs = delta["tool_calls"]
            if isinstance(tcs, list) and tcs:
                tc0 = tcs[0] if isinstance(tcs[0], dict) else {}
                fn = tc0.get("function") if isinstance(tc0.get("function"), dict) else {}
                if not tool_block_open:
                    tool_index = int(tc0.get("index") or 0)
                    tid = tc0.get("id") or f"toolu_{uuid.uuid4().hex[:20]}"
                    name = fn.get("name") or ""
                    yield _sse_event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": tool_index,
                            "content_block": {
                                "type": "tool_use",
                                "id": str(tid),
                                "name": str(name),
                                "input": {},
                            },
                        },
                    )
                    tool_block_open = True
                    pending_tool = {"id": tid, "name": name, "arguments": fn.get("arguments") or ""}
                args = fn.get("arguments")
                if args and pending_tool is not None:
                    pending_tool["arguments"] = str(args)
                    yield _sse_event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": tool_index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": str(args),
                            },
                        },
                    )
                    out_tokens_est = max(out_tokens_est, len(str(args)) // 4)

        if isinstance(delta.get("content"), str) and delta["content"]:
            if not text_block_open and not tool_block_open:
                yield _sse_event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
                text_block_open = True
            if text_block_open:
                piece = delta["content"]
                yield _sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": piece},
                    },
                )
                out_tokens_est += max(1, len(piece) // 4)

        if finish:
            last_finish = str(finish)
            if text_block_open:
                yield _sse_event(
                    "content_block_stop", {"type": "content_block_stop", "index": 0}
                )
                text_block_open = False
            if tool_block_open:
                yield _sse_event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": tool_index},
                )
                tool_block_open = False
                pending_tool = None


def anthropic_stream_from_openai_completion_dict(
    openai_resp: dict[str, Any],
    *,
    stream_model: str,
) -> Iterator[str]:
    """Synthesize Anthropic SSE from a single non-streaming OpenAI chat.completion object."""
    am = openai_chat_completion_to_anthropic_message(openai_resp)
    msg_id = am["id"]
    model = stream_model or str(am.get("model") or "")
    usage = am.get("usage") if isinstance(am.get("usage"), dict) else {}
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)

    yield _sse_event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": in_tok, "output_tokens": max(1, out_tok)},
            },
        },
    )

    blocks = am.get("content")
    if not isinstance(blocks, list):
        blocks = []
    idx = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            text = str(block.get("text") or "")
            yield _sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": idx,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            if text:
                yield _sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": idx,
                        "delta": {"type": "text_delta", "text": text},
                    },
                )
            yield _sse_event(
                "content_block_stop", {"type": "content_block_stop", "index": idx}
            )
            idx += 1
        elif bt == "tool_use":
            tid = block.get("id") or f"toolu_{uuid.uuid4().hex[:20]}"
            name = str(block.get("name") or "")
            inp = block.get("input")
            args = json.dumps(inp if isinstance(inp, dict) else {}, ensure_ascii=False)
            yield _sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": idx,
                    "content_block": {
                        "type": "tool_use",
                        "id": str(tid),
                        "name": name,
                        "input": {},
                    },
                },
            )
            yield _sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": idx,
                    "delta": {"type": "input_json_delta", "partial_json": args},
                },
            )
            yield _sse_event(
                "content_block_stop", {"type": "content_block_stop", "index": idx}
            )
            idx += 1

    sr = str(am.get("stop_reason") or "end_turn")
    yield _sse_event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": sr, "stop_sequence": None},
            "usage": {"output_tokens": max(1, out_tok)},
        },
    )
    yield _sse_event("message_stop", {"type": "message_stop"})


def wants_anthropic_models_list(headers: Any) -> bool:
    """True when GET /v1/models should return Anthropic-shaped JSON."""
    if headers is None:
        return False
    try:
        v = headers.get("Anthropic-Version") or headers.get("anthropic-version")
    except Exception:
        return False
    return bool(str(v or "").strip())
