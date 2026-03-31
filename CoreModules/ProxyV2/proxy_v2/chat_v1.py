"""POST /v1/chat/completions — OpenAI-shaped bridge to Ollama /api/chat."""

from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from copy import deepcopy
from typing import Any

from flask import Response, jsonify, request

from proxy_v2.contracts import ProxyV2Wiring
from proxy_v2.trace_store import append_stream_line, new_trace, phase, record_error, set_current_trace

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def _normalize_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("messages")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for m in raw:
        if isinstance(m, dict):
            out.append(m)
    logger.debug(f"Normalized messages: {out}")
    return out


def run_v1_chat_completions(w: ProxyV2Wiring) -> Response | tuple[Response, int]:
    tid = f"v2-{uuid.uuid4().hex[:12]}"
    tr = new_trace(tid)
    tr["request"]["path"] = request.path
    set_current_trace(tr)

    try:
        body = request.get_json(force=True, silent=True) or {}
        logger.debug(f"Received request body: {body}")
    except Exception as e:
        record_error(tr, str(e), traceback.format_exc())
        set_current_trace(tr)
        return jsonify({"error": "Invalid JSON"}), 400

    messages = _normalize_messages(body)
    if not messages:
        return jsonify({"error": "messages is required"}), 400

    tr["request"]["openai_body"] = deepcopy(body)

    stream = bool(body.get("stream", False))
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    tool_choice = body.get("tool_choice")
    tool_choice_effective = tool_choice if tool_choice not in (None, "") else "auto"
    disable_native_env = os.getenv("PROXY_V2_DISABLE_NATIVE_TOOLS", "").strip().lower()
    disable_native = disable_native_env in ("1", "true", "yes", "on")
    use_native_tools = bool(tools) and tool_choice_effective != "none" and not disable_native
    include_metadata = bool(body.get("include_rag_metadata", False))

    pinned = (w.get_pinned_model() or "").strip()
    req_model = str(body.get("model") or "").strip()
    use_model = pinned or req_model
    tr["request"]["model_requested"] = req_model or body.get("model")
    tr["request"]["model_resolved"] = use_model
    if not use_model:
        return jsonify({"error": "model is required (or set Proxy V2 pinned model in WebUI)"}), 400

    tr["upstream"]["url"] = w.get_ollama_chat_url()
    set_current_trace(tr)

    ollama_messages = w.openai_messages_to_ollama(messages)
    ollama_think = body.get("think")
    default_opts = w.get_default_chat_options() or {}

    # Map a subset of OpenAI sampling params onto Ollama options on top of defaults.
    mapped_opts: dict[str, Any] = dict(default_opts)
    if body.get("temperature") is not None:
        try:
            mapped_opts["temperature"] = float(body["temperature"])
        except (TypeError, ValueError):
            pass
    if body.get("top_p") is not None:
        try:
            mapped_opts["top_p"] = float(body["top_p"])
        except (TypeError, ValueError):
            pass
    mt = body.get("max_completion_tokens")
    if mt is None:
        mt = body.get("max_tokens")
    if mt is not None:
        try:
            mapped_opts["num_predict"] = int(mt)
        except (TypeError, ValueError):
            pass

    phase(tr, "openai_parsed", stream=stream, native_tools=use_native_tools)
    tr["upstream"]["ollama_messages_count"] = len(ollama_messages)
    logger.debug(f"Ollama messages count: {len(ollama_messages)}")

    try:
        if use_native_tools:
            oll_tools = w.ollama_tools_from_openai([t for t in tools if isinstance(t, dict)])
            # Ollama: always non-streaming /api/chat; we aggregate one JSON response then adapt to OpenAI SSE if needed.
            body_ollama: dict[str, Any] = {
                "model": use_model,
                "messages": ollama_messages,
                "stream": False,
                "options": dict(mapped_opts),
            }
            if ollama_think is not None:
                body_ollama["think"] = ollama_think
            if oll_tools:
                body_ollama["tools"] = oll_tools
            if tool_choice_effective not in (None, "", "auto"):
                body_ollama["tool_choice"] = tool_choice_effective

            tr["upstream"]["body"] = deepcopy(body_ollama)
            tr["upstream"]["body_summary"] = {
                "model": use_model,
                "stream": False,
                "client_stream": stream,
                "tools_count": len(oll_tools or []),
            }
            logger.debug(f"Body summary: {tr['upstream']['body_summary']}")
            set_current_trace(tr)

            data = w.chat_api(body_ollama)
            logger.debug(f"Ollama chat data received (stream=False): {data}")

            err_obj = data.get("error")
            if err_obj:
                logger.error(f"Error from Ollama: {err_obj}")
                return jsonify({"error": str(err_obj)}), 502
            oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
            if not oll_msg:
                logger.error("Ollama returned no assistant message")
                return jsonify({"error": "Ollama returned no assistant message"}), 502
            logger.debug(f"Ollama message: {oll_msg}")

            openai_msg = w.ollama_message_to_openai_assistant(oll_msg)
            finish = w.openai_finish_reason_from_ollama(oll_msg)
            tool_calls_out = openai_msg.get("tool_calls") if isinstance(openai_msg.get("tool_calls"), list) else []
            content_out = openai_msg.get("content")
            content_str = (
                content_out if isinstance(content_out, str) else ("" if content_out is None else str(content_out))
            )

            if stream:

                def generate_sse_native():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    append_stream_line(tr, "[sse] role assistant")
                    set_current_trace(tr)
                    if tool_calls_out:
                        payload_calls: list[dict[str, Any]] = []
                        for i, tc in enumerate(tool_calls_out):
                            if not isinstance(tc, dict):
                                continue
                            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                            payload_calls.append(
                                {
                                    "index": i,
                                    "id": tc.get("id"),
                                    "type": "function",
                                    "function": {
                                        "name": fn.get("name"),
                                        "arguments": fn.get("arguments"),
                                    },
                                }
                            )
                        line = f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'tool_calls': payload_calls}, 'finish_reason': None}]})}\n\n"
                        append_stream_line(tr, line.strip())
                        yield line
                        line2 = f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                        append_stream_line(tr, line2.strip())
                        yield line2
                    else:
                        if content_str:
                            line = f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'content': content_str}, 'finish_reason': None}]})}\n\n"
                            append_stream_line(tr, line.strip())
                            yield line
                        # Only yield finish chunk if we actually sent content
                        if content_str or tool_calls_out:
                            logger.debug(f"Yielding finish chunk with finish_reason: {finish}")
                            line3 = f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})}\n\n"
                            append_stream_line(tr, line3.strip())
                            yield line3
                        else:
                            logger.debug("Skipping finish chunk - no content or tool calls")
                    yield "data: [DONE]\n\n"
                    phase(tr, "sse_complete")
                    set_current_trace(tr)

                return Response(
                    generate_sse_native(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            choice_msg: dict[str, Any] = {
                "role": "assistant",
                "content": None if tool_calls_out else (content_str or None),
            }
            if tool_calls_out:
                choice_msg["tool_calls"] = tool_calls_out
            response_data: dict[str, Any] = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion",
                "created": 0,
                "model": use_model,
                "choices": [
                    {
                        "index": 0,
                        "message": choice_msg,
                        "finish_reason": finish,
                    }
                ],
            }
            if include_metadata:
                response_data["rag_metadata"] = {}
            phase(tr, "complete")
            set_current_trace(tr)
            return jsonify(response_data)

        # No native tools — Ollama always non-stream; OpenAI client may still request SSE (synthesized below).
        body_ollama = {
            "model": use_model,
            "messages": ollama_messages,
            "stream": False,
            "options": dict(mapped_opts),
        }
        if ollama_think is not None:
            body_ollama["think"] = ollama_think

        tr["upstream"]["body"] = deepcopy(body_ollama)
        tr["upstream"]["url"] = tr["upstream"].get("url") or w.get_ollama_chat_url()
        set_current_trace(tr)

        if stream:

            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                logger.debug(f"Starting SSE generation (Ollama stream=False) with model: {use_model}")
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                content_sent = False
                try:
                    data = w.chat_api({**body_ollama, "stream": False})
                    err_obj = data.get("error")
                    if err_obj:
                        raise RuntimeError(str(err_obj))
                    oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
                    if not oll_msg:
                        raise RuntimeError("Ollama returned no assistant message")
                    openai_msg = w.ollama_message_to_openai_assistant(oll_msg)
                    finish = w.openai_finish_reason_from_ollama(oll_msg)
                    content_out = openai_msg.get("content")
                    text = (
                        content_out
                        if isinstance(content_out, str)
                        else ("" if content_out is None else str(content_out))
                    )
                    if text:
                        content_sent = True
                        chunk = {
                            "id": oid,
                            "object": "chat.completion.chunk",
                            "model": use_model,
                            "choices": [
                                {"index": 0, "delta": {"content": text}, "finish_reason": None},
                            ],
                        }
                        line = f"data: {json.dumps(chunk)}\n\n"
                        append_stream_line(tr, line.strip())
                        set_current_trace(tr)
                        yield line
                    if content_sent:
                        logger.debug("Yielding finish chunk for SSE")
                        yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})}\n\n"
                    else:
                        logger.debug("Skipping finish chunk for SSE - no content sent")
                except Exception as e:
                    record_error(tr, str(e), traceback.format_exc())
                    set_current_trace(tr)
                    raise
                yield "data: [DONE]\n\n"
                phase(tr, "sse_complete")
                set_current_trace(tr)

            return Response(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        data = w.chat_api({**body_ollama, "stream": False})
        err_obj = data.get("error")
        if err_obj:
            return jsonify({"error": str(err_obj)}), 502
        oll_msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        if not oll_msg:
            return jsonify({"error": "Ollama returned no assistant message"}), 502
        openai_msg = w.ollama_message_to_openai_assistant(oll_msg)
        finish = w.openai_finish_reason_from_ollama(oll_msg)
        tool_calls_out = openai_msg.get("tool_calls") if isinstance(openai_msg.get("tool_calls"), list) else []
        content_out = openai_msg.get("content")
        content_str = content_out if isinstance(content_out, str) else ("" if content_out is None else str(content_out))
        choice_msg = {
            "role": "assistant",
            "content": None if tool_calls_out else (content_str or None),
        }
        if tool_calls_out:
            choice_msg["tool_calls"] = tool_calls_out
        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": use_model,
            "choices": [{"index": 0, "message": choice_msg, "finish_reason": finish}],
        }
        if include_metadata:
            response_data["rag_metadata"] = {}
        phase(tr, "complete")
        set_current_trace(tr)
        return jsonify(response_data)

    except Exception as e:
        record_error(tr, str(e), traceback.format_exc())
        set_current_trace(tr)
        return jsonify({"error": str(e)}), 500


__all__ = ["run_v1_chat_completions"]
