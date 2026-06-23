"""Responses API compatibility helpers for /v1 routes."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from flask import Response

_RESPONSES_HISTORY: dict[str, list[dict[str, Any]]] = {}
_RESPONSES_CHAIN_IDS: dict[str, str] = {}
_RESPONSES_HISTORY_MAX = 200


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        s = str(value).strip()
        if s:
            return s
    return ""


def _responses_explicit_chain_id(raw: dict[str, Any]) -> str:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return _first_non_empty(
        raw.get("client_request_id"),
        raw.get("trace_chain_id"),
        raw.get("chain_id"),
        metadata.get("trace_chain_id"),
        metadata.get("chain_id"),
        metadata.get("conversation_id"),
        metadata.get("thread_id"),
        metadata.get("session_id"),
    )


def _responses_chain_id_for_request(raw: dict[str, Any], inbound_request_id: str = "") -> str:
    explicit = _responses_explicit_chain_id(raw)
    if explicit:
        return explicit

    previous_response_id = str(raw.get("previous_response_id") or "").strip()
    if previous_response_id:
        previous_chain = str(_RESPONSES_CHAIN_IDS.get(previous_response_id) or "").strip()
        if previous_chain:
            return previous_chain
        return f"responses:{previous_response_id}"

    inbound = str(inbound_request_id or "").strip()
    if inbound:
        return inbound

    return f"responses:{uuid.uuid4().hex[:12]}"


def _responses_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "").strip()
            if ptype in {"input_text", "output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str) and text:
                    out.append(text)
        return "".join(out)
    return ""


def _responses_input_to_openai_messages(raw_input: Any) -> list[dict[str, Any]]:
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if not isinstance(raw_input, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_input:
        if not isinstance(item, dict):
            continue
        itype = str(item.get("type") or "").strip()
        if itype == "function_call":
            # Responses API assistant tool-call item â†’ OpenAI Chat assistant message with tool_calls.
            # Must be preserved in the message list so _build_tool_call_id_to_name can resolve the
            # function name when processing the corresponding function_call_output below.
            call_id = str(item.get("call_id") or item.get("id") or "").strip()
            fn_name = str(item.get("name") or "").strip()
            if fn_name:
                tc_id = call_id or f"call_{uuid.uuid4().hex[:24]}"
                out.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc_id,
                        "call_id": call_id or tc_id,
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": str(item.get("arguments") or "{}"),
                        },
                    }],
                })
            continue
        if itype == "function_call_output":
            call_id = str(
                item.get("call_id")
                or item.get("tool_call_id")
                or item.get("tool_callid")
                or item.get("id")
                or ""
            ).strip()
            tool_output = item.get("output")
            if isinstance(tool_output, (dict, list)):
                tool_content = json.dumps(tool_output, ensure_ascii=False)
            else:
                tool_content = str(tool_output or "")
            if not tool_content:
                continue
            msg: dict[str, Any] = {"role": "tool", "content": tool_content}
            if call_id:
                msg["tool_call_id"] = call_id
            tool_name = str(item.get("name") or item.get("tool_name") or "").strip()
            if tool_name:
                # Preserve both aliases for downstream bridges that require one or the other.
                msg["name"] = tool_name
                msg["tool_name"] = tool_name
            out.append(msg)
            continue
        if itype == "message":
            role = str(item.get("role") or "user").strip() or "user"
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            text = _responses_content_to_text(item.get("content"))
            if text:
                out.append({"role": role, "content": text})
            continue
        role = str(item.get("role") or "").strip()
        if role:
            text = _responses_content_to_text(item.get("content"))
            if text:
                out.append({"role": role, "content": text})
    return out


def _responses_responses_function_tool_to_chat_shape(tool: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map a Responses API ``{"type":"function", ...}`` tool to **OpenAI Chat Completions**
    tool shape ``{"type":"function","function":{...}}``.

    OpenAI documents that Responses uses **internally-tagged** function objects (``name``,
    ``description``, ``parameters``, ``strict`` on the same object as ``type``), while
    Chat Completions use **externally-tagged** nesting under ``function``.
    Clients using Responses-style tools (``wire_api = "responses"``) follow that shape. Our stack still calls
    ``run_chat_completions`` / Ollama with the Chat tool wire â€” so this mapping is required.

    See: https://developers.openai.com/docs/guides/migrate-to-responses (section *Update function definitions*).
    """
    fn_in = tool.get("function")
    fn: dict[str, Any] = dict(fn_in) if isinstance(fn_in, dict) else {}
    name = str(fn.get("name") or tool.get("name") or "").strip()
    if not name:
        return None
    if "description" not in fn or fn.get("description") in (None, ""):
        d = tool.get("description")
        if isinstance(d, str) and d.strip():
            fn["description"] = d.strip()
    if "parameters" not in fn or not isinstance(fn.get("parameters"), dict):
        params = tool.get("parameters")
        if not isinstance(params, dict):
            params = tool.get("input_schema")
        if not isinstance(params, dict):
            params = tool.get("json_schema")
        if isinstance(params, dict):
            fn["parameters"] = params
        else:
            fn["parameters"] = {"type": "object", "additionalProperties": True}
    fn.setdefault("name", name)
    # Responses defaults strict=true for functions; preserve when present on either level.
    if "strict" not in fn and "strict" in tool:
        fn["strict"] = tool["strict"]
    return {"type": "function", "function": fn}


def _responses_shell_function_tool(*, description: str | None) -> dict[str, Any]:
    """OpenAI-chat ``function`` tool for shell execution (local client harness)."""
    return {
        "type": "function",
        "function": {
            "name": "shell",
            "description": str(
                description or "Run shell command in workspace (e.g. `start https://...` on Windows to open a URL in the browser)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "workdir": {"type": "string"},
                    "timeout_ms": {"type": "integer", "minimum": 1},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    }


def _responses_normalize_tools(tools: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Convert ``tools`` from a **Responses** ``POST /v1/responses`` body into **Chat Completions**
    ``tools`` for ``run_chat_completions`` / Ollama.

    Not optional: Responses native entries (``web_search``, ``local_shell``, ``custom``, â€¦)
    are not valid Chat ``tools``; ``type: "function"`` uses internally-tagged layout and
    must be re-shaped (see ``_responses_responses_function_tool_to_chat_shape``).
    """
    raw_types: list[str] = []
    normalized_types: list[str] = []
    dropped_types: list[str] = []
    if not isinstance(tools, list):
        return [], {
            "tools_count_raw": 0,
            "tools_count_normalized": 0,
            "tools_types_raw": raw_types,
            "tools_types_dropped": dropped_types,
            "tools_types_normalized": normalized_types,
        }

    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            dropped_types.append("invalid")
            continue
        t = str(tool.get("type") or "").strip()
        raw_types.append(t or "unknown")

        if t == "function":
            coerced = _responses_responses_function_tool_to_chat_shape(tool)
            if coerced is None:
                dropped_types.append("function")
                continue
            fn = coerced.get("function")
            if not isinstance(fn, dict):
                dropped_types.append("function")
                continue
            name = str(fn.get("name") or "").strip()
            if not name:
                dropped_types.append("function")
                continue
            if name not in seen_names:
                out.append(coerced)
                seen_names.add(name)
                normalized_types.append("function")
            continue

        if t in {"local_shell", "shell"}:
            name = "shell"
            if name not in seen_names:
                out.append(
                    _responses_shell_function_tool(
                        description=(
                            tool.get("description")
                            if isinstance(tool.get("description"), str)
                            else None
                        ),
                    )
                )
                seen_names.add(name)
                normalized_types.append(f"{t}->function")
            continue

        if t == "web_search":
            name = "web_search"
            if name not in seen_names:
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": str(
                                tool.get("description")
                                or "Search the web for up-to-date information. The client executes this tool locally; Chiron can inject supplementary web context when fetch_web_knowledge is enabled on the proxy."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Search query."},
                                    "max_results": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 20,
                                        "description": "Optional cap on result snippets.",
                                    },
                                },
                                "required": ["query"],
                                "additionalProperties": False,
                            },
                        },
                    }
                )
                seen_names.add(name)
                normalized_types.append("web_search->function")
            continue

        if t == "file_search":
            name = "file_search"
            if name not in seen_names:
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": str(
                                tool.get("description")
                                or "Search files in the workspace. Executed by the local client or IDE harness."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "paths": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional path globs or roots to search.",
                                    },
                                },
                                "required": ["query"],
                                "additionalProperties": True,
                            },
                        },
                    }
                )
                seen_names.add(name)
                normalized_types.append("file_search->function")
            continue

        if t == "computer_use":
            name = "computer_use"
            if name not in seen_names:
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": str(
                                tool.get("description")
                                or "Computer-use UI automation. Executed by the local client when supported; otherwise the harness may decline."
                            ),
                            "parameters": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                        },
                    }
                )
                seen_names.add(name)
                normalized_types.append("computer_use->function")
            continue

        if t == "custom":
            name = str(tool.get("name") or "").strip()
            if not name:
                dropped_types.append("custom")
                continue
            params = tool.get("input_schema")
            if not isinstance(params, dict):
                params = tool.get("parameters")
            if not isinstance(params, dict):
                params = {"type": "object", "additionalProperties": True}
            if name not in seen_names:
                out.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": str(tool.get("description") or ""),
                            "parameters": params,
                        },
                    }
                )
                seen_names.add(name)
                normalized_types.append("custom->function")
            continue

        dropped_types.append(t or "unknown")

    return out, {
        "tools_count_raw": len(tools),
        "tools_count_normalized": len(out),
        "tools_types_raw": raw_types,
        "tools_types_dropped": dropped_types,
        "tools_types_normalized": normalized_types,
    }


def _responses_tool_choice_to_chat(tool_choice: Any, available_function_names: set[str]) -> Any:
    if isinstance(tool_choice, str):
        if tool_choice in {"none", "auto", "required"}:
            return tool_choice
        return None
    if not isinstance(tool_choice, dict):
        return None
    t = str(tool_choice.get("type") or "").strip()
    if t in {"none", "auto", "required"}:
        return t
    if t == "function":
        fn = tool_choice.get("function")
        name = str(fn.get("name") or "").strip() if isinstance(fn, dict) else ""
        if not name:
            name = str(tool_choice.get("name") or "").strip()
        if name and name in available_function_names:
            return {"type": "function", "function": {"name": name}}
    if t == "custom":
        name = str(tool_choice.get("name") or "").strip()
        if name and name in available_function_names:
            return {"type": "function", "function": {"name": name}}
    if t in {"local_shell", "shell"} and "shell" in available_function_names:
        return {"type": "function", "function": {"name": "shell"}}
    if t == "web_search" and "web_search" in available_function_names:
        return {"type": "function", "function": {"name": "web_search"}}
    if t == "file_search" and "file_search" in available_function_names:
        return {"type": "function", "function": {"name": "file_search"}}
    if t == "computer_use" and "computer_use" in available_function_names:
        return {"type": "function", "function": {"name": "computer_use"}}
    return None


def _responses_request_to_openai_chat_body(raw: dict[str, Any]) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    incoming = _responses_input_to_openai_messages(raw.get("input"))
    instructions = str(raw.get("instructions") or "").strip()
    if instructions:
        incoming = [{"role": "system", "content": instructions}, *incoming]

    previous_response_id = str(raw.get("previous_response_id") or "").strip()
    history = list(_RESPONSES_HISTORY.get(previous_response_id, [])) if previous_response_id else []
    messages = [*history, *incoming]

    body: dict[str, Any] = {
        "model": str(raw.get("model") or ""),
        "messages": messages,
        # We always call chat handler in non-stream mode and synthesize Responses-SSE.
        "stream": False,
    }
    if isinstance(raw.get("temperature"), (int, float)):
        body["temperature"] = raw.get("temperature")
    if isinstance(raw.get("top_p"), (int, float)):
        body["top_p"] = raw.get("top_p")
    if isinstance(raw.get("max_output_tokens"), int):
        body["max_tokens"] = raw.get("max_output_tokens")

    tools, diag = _responses_normalize_tools(raw.get("tools"))
    if tools:
        body["tools"] = tools
    tool_choice = _responses_tool_choice_to_chat(
        raw.get("tool_choice"),
        {
            str((((tool or {}).get("function") or {}).get("name") or "").strip())
            for tool in tools
            if isinstance(tool, dict)
        }
        - {""},
    )
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    diag["tool_choice_raw"] = raw.get("tool_choice")
    diag["tool_choice_normalized"] = tool_choice
    body.update(
        {
            "tools_count_raw": diag.get("tools_count_raw"),
            "tools_count_normalized": diag.get("tools_count_normalized"),
            "tools_types_raw": diag.get("tools_types_raw"),
            "tools_types_dropped": diag.get("tools_types_dropped"),
            "tools_types_normalized": diag.get("tools_types_normalized"),
            "tool_choice_raw": diag.get("tool_choice_raw"),
            "tool_choice_normalized": diag.get("tool_choice_normalized"),
        }
    )
    # Stripped in ``run_chat_completions`` before upstream; copied into ``trace["request"]`` for logs/UI.
    body["_proxy_trace_meta"] = {
        "proxy_v1_route": "/v1/responses",
        "responses_client_stream": bool(raw.get("stream", False)),
    }
    return body, bool(raw.get("stream", False)), diag


def _chat_message_to_responses_output_items(message: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    output: list[dict[str, Any]] = []
    text_parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        text_parts.append(content)
    elif isinstance(content, list):
        for p in content:
            if isinstance(p, dict):
                t = p.get("text")
                if isinstance(t, str) and t:
                    text_parts.append(t)
    merged_text = "".join(text_parts)
    if merged_text:
        output.append(
            {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": merged_text, "annotations": []}],
            }
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            tc_id = str(tc.get("id") or "").strip()
            tc_call_id = str(tc.get("call_id") or "").strip()
            stable_id = tc_id or tc_call_id or f"call_{uuid.uuid4().hex[:24]}"
            stable_call_id = tc_call_id or stable_id
            output.append(
                {
                    "id": stable_id,
                    "type": "function_call",
                    "status": "completed",
                    "name": name,
                    "arguments": str(fn.get("arguments") or ""),
                    "call_id": stable_call_id,
                }
            )
    return output, merged_text


def _chat_completion_to_responses_json(
    oa_json: dict[str, Any],
    requested_model: str,
    raw_request: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = str(oa_json.get("model") or requested_model or "")
    choices = oa_json.get("choices") or []
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if not isinstance(message, dict):
        message = {}
    output_items, output_text = _chat_message_to_responses_output_items(message)
    usage = oa_json.get("usage") if isinstance(oa_json.get("usage"), dict) else {}
    in_tokens = int(usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (in_tokens + out_tokens))

    out = {
        "id": resp_id,
        "object": "response",
        "created_at": created,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": raw_request.get("instructions"),
        "max_output_tokens": raw_request.get("max_output_tokens"),
        "model": model,
        "output": output_items,
        "output_text": output_text,
        "parallel_tool_calls": bool(raw_request.get("parallel_tool_calls", True)),
        "previous_response_id": raw_request.get("previous_response_id"),
        "reasoning": {"effort": None, "summary": None},
        "temperature": raw_request.get("temperature"),
        "text": {"format": {"type": "text"}},
        "tool_choice": raw_request.get("tool_choice") or "auto",
        "tools": raw_request.get("tools") or [],
        "top_p": raw_request.get("top_p"),
        "usage": {
            "input_tokens": in_tokens,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": out_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": total_tokens,
        },
    }
    assistant_msg: dict[str, Any] = {"role": "assistant"}
    if output_text:
        assistant_msg["content"] = output_text
    tc = message.get("tool_calls")
    if isinstance(tc, list) and tc:
        assistant_msg["tool_calls"] = tc
    return out, [assistant_msg]


def _responses_sse_payload(out: dict[str, Any]) -> Response:
    rid = str(out.get("id") or f"resp_{uuid.uuid4().hex[:24]}")
    model = str(out.get("model") or "")
    output = out.get("output") or []
    if not isinstance(output, list):
        output = []

    events: list[dict[str, Any]] = [
        {
            "type": "response.created",
            "response": {"id": rid, "object": "response", "model": model, "status": "in_progress"},
        },
        {
            "type": "response.in_progress",
            "response": {"id": rid, "object": "response", "model": model, "status": "in_progress"},
        },
    ]

    for idx, item in enumerate(output):
        if not isinstance(item, dict):
            continue
        itype = str(item.get("type") or "").strip()
        if itype == "message":
            content_list = item.get("content") if isinstance(item.get("content"), list) else []
            text = ""
            if isinstance(content_list, list) and content_list:
                first = content_list[0]
                if isinstance(first, dict):
                    text = str(first.get("text") or "")
            mid = str(item.get("id") or f"msg_{uuid.uuid4().hex[:24]}")
            events.extend(
                [
                    {
                        "type": "response.output_item.added",
                        "response_id": rid,
                        "output_index": idx,
                        "item": {
                            "id": mid,
                            "type": "message",
                            "role": "assistant",
                            "status": "in_progress",
                            "content": [],
                        },
                    },
                    {
                        "type": "response.content_part.added",
                        "response_id": rid,
                        "output_index": idx,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": ""},
                    },
                    {
                        "type": "response.output_text.delta",
                        "response_id": rid,
                        "output_index": idx,
                        "content_index": 0,
                        "delta": text,
                    },
                    {
                        "type": "response.output_text.done",
                        "response_id": rid,
                        "output_index": idx,
                        "content_index": 0,
                        "text": text,
                    },
                    {
                        "type": "response.content_part.done",
                        "response_id": rid,
                        "output_index": idx,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": text},
                    },
                    {
                        "type": "response.output_item.done",
                        "response_id": rid,
                        "output_index": idx,
                        # Full item (incl. content) â€” some Responses clients render from ``output_item.done`` only.
                        "item": item,
                    },
                ]
            )
        elif itype == "function_call":
            cid = str(item.get("id") or item.get("call_id") or f"call_{uuid.uuid4().hex[:24]}")
            call_id = str(item.get("call_id") or cid)
            name = str(item.get("name") or "")
            events.extend(
                [
                    {
                        "type": "response.output_item.added",
                        "response_id": rid,
                        "output_index": idx,
                        "item": {
                            "id": cid,
                            "type": "function_call",
                            "status": "in_progress",
                            "name": name,
                            "call_id": call_id,
                        },
                    },
                    {
                        "type": "response.output_item.done",
                        "response_id": rid,
                        "output_index": idx,
                        "item": item,
                    },
                ]
            )

    events.append({"type": "response.completed", "response": out})

    def _gen():
        import json

        for e in events:
            yield f"event: {e['type']}\n"
            yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        _gen(),
        mimetype="text/event-stream",
        status=200,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _responses_history_put(resp_id: str, messages: list[dict[str, Any]]) -> None:
    if not resp_id:
        return
    _RESPONSES_HISTORY[resp_id] = messages[-200:]
    if len(_RESPONSES_HISTORY) > _RESPONSES_HISTORY_MAX:
        for k in list(_RESPONSES_HISTORY.keys())[: len(_RESPONSES_HISTORY) - _RESPONSES_HISTORY_MAX]:
            _RESPONSES_HISTORY.pop(k, None)
            _RESPONSES_CHAIN_IDS.pop(k, None)


def _responses_chain_id_put(resp_id: str, chain_id: str) -> None:
    resp = str(resp_id or "").strip()
    chain = str(chain_id or "").strip()
    if not resp or not chain:
        return
    _RESPONSES_CHAIN_IDS[resp] = chain
    if len(_RESPONSES_HISTORY) <= _RESPONSES_HISTORY_MAX:
        return
    for k in list(_RESPONSES_HISTORY.keys())[: len(_RESPONSES_HISTORY) - _RESPONSES_HISTORY_MAX]:
        _RESPONSES_HISTORY.pop(k, None)
        _RESPONSES_CHAIN_IDS.pop(k, None)

__all__ = [
    "_RESPONSES_CHAIN_IDS",
    "_RESPONSES_HISTORY",
    "_RESPONSES_HISTORY_MAX",
    "_chat_completion_to_responses_json",
    "_chat_message_to_responses_output_items",
    "_responses_chain_id_for_request",
    "_responses_chain_id_put",
    "_responses_content_to_text",
    "_responses_explicit_chain_id",
    "_responses_history_put",
    "_responses_input_to_openai_messages",
    "_responses_normalize_tools",
    "_responses_request_to_openai_chat_body",
    "_responses_responses_function_tool_to_chat_shape",
    "_responses_shell_function_tool",
    "_responses_sse_payload",
    "_responses_tool_choice_to_chat",
]

