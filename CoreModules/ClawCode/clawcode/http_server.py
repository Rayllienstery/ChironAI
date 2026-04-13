"""Flask app: OpenAI-compatible /v1/chat/completions and Anthropic /v1/messages for ClawCode agent."""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

# Monorepo: allow ``import llm_proxy`` without a separate ``pip install -e`` when this path exists.
_llm_proxy_src = Path(__file__).resolve().parents[3] / "CoreModules" / "LlmProxy"
if _llm_proxy_src.is_dir():
    _lp = str(_llm_proxy_src)
    if _lp not in sys.path:
        sys.path.insert(0, _lp)
_rag_svc_src = Path(__file__).resolve().parents[3] / "CoreModules" / "RagService"
if _rag_svc_src.is_dir():
    _rs = str(_rag_svc_src)
    if _rs not in sys.path:
        sys.path.insert(0, _rs)

from flask import Flask, Response, jsonify, request

from llm_proxy.anthropic_compat import (
    anthropic_messages_request_to_openai_body,
    anthropic_models_list_payload,
    anthropic_stream_from_openai_completion_dict,
    openai_chat_completion_to_anthropic_message,
    wants_anthropic_models_list,
)

from clawcode.agent_runner import iter_clawcode_agent_sse, run_clawcode_chat_completion
from clawcode.trace_journal import persist_clawcode_trace_to_db
from clawcode.trace_store import append as trace_append

_LOG = logging.getLogger("clawcode.http")


def _chiron_private_mode_from_request() -> bool:
    v = (request.headers.get("X-Chiron-Private") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _openai_message_content_to_str(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                t = p.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)


def _openai_sse_chunks_from_completion(resp: dict) -> Iterator[str]:
    """
    Emit OpenAI-compatible SSE chunks from a non-streaming chat.completion dict.
    Used when clients (e.g. VS Code Copilot) send ``stream: true`` but the agent
    returns one assembled completion.
    """
    oid = str(resp.get("id") or f"chatcmpl-{uuid.uuid4().hex[:24]}")
    model = str(resp.get("model") or "")
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        yield f"data: {json.dumps({'error': {'message': 'invalid completion: no choices', 'type': 'api_error'}})}\n\n"
        return
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        yield f"data: {json.dumps({'error': {'message': 'invalid completion', 'type': 'api_error'}})}\n\n"
        return
    msg = ch0.get("message")
    if not isinstance(msg, dict):
        msg = {}
    finish = ch0.get("finish_reason") or "stop"
    if not isinstance(finish, str):
        finish = "stop"

    yield (
        "data: "
        + json.dumps(
            {
                "id": oid,
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None,
                    }
                ],
            }
        )
        + "\n\n"
    )

    tool_calls = msg.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        payload_calls: list[dict[str, object]] = []
        for i, tc in enumerate(tool_calls):
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            payload_calls.append(
                {
                    "index": i,
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": fn.get("name") if isinstance(fn, dict) else None,
                        "arguments": fn.get("arguments") if isinstance(fn, dict) else None,
                    },
                }
            )
        yield (
            "data: "
            + json.dumps(
                {
                    "id": oid,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"tool_calls": payload_calls},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            + "\n\n"
        )
        yield (
            "data: "
            + json.dumps(
                {
                    "id": oid,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            )
            + "\n\n"
        )
    else:
        content_str = _openai_message_content_to_str(msg.get("content"))
        if content_str:
            yield (
                "data: "
                + json.dumps(
                    {
                        "id": oid,
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content_str},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
                + "\n\n"
            )
        yield (
            "data: "
            + json.dumps(
                {
                    "id": oid,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": finish,
                        }
                    ],
                }
            )
            + "\n\n"
        )

    yield "data: [DONE]\n\n"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_webui_dir() -> str:
    env = os.environ.get("CHIRONAI_WEBUI_DIR", "").strip()
    if env:
        return env
    return str(project_root() / "WebUI")


def _clawcode_openai_models_rows() -> list[dict[str, object]]:
    """Ollama model rows for OpenAI-shaped ``GET /v1/models`` ``data`` (no synthetic logical id)."""
    data: list[dict[str, object]] = []
    try:
        from config import get_ollama_base_url, get_ollama_chat_model
        from infrastructure.ollama.cli_runner import invoke_tags
        from infrastructure.ollama.ollama_model_visibility import get_hidden_ollama_model_ids

        base_url = get_ollama_base_url()
        hidden = get_hidden_ollama_model_ids()
        tags = invoke_tags(base_url=base_url, timeout=5.0)
        models = tags.get("models") or []
        seen: set[str] = set()
        for m in models:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or m.get("model") or "").strip()
            if not name or name in seen or name in hidden:
                continue
            seen.add(name)
            data.append({"id": name, "object": "model", "owned_by": "ollama"})
        cfg_model = get_ollama_chat_model()
        if cfg_model and cfg_model not in seen and cfg_model not in hidden:
            data.insert(0, {"id": cfg_model, "object": "model", "owned_by": "ollama"})
    except Exception:
        try:
            from config import get_ollama_chat_model

            cfg_model = get_ollama_chat_model()
        except Exception:
            cfg_model = "unknown"
        data = [{"id": cfg_model, "object": "model", "owned_by": "ollama"}]
    return data


def create_clawcode_flask_app() -> Flask:
    app = Flask(__name__)
    webui_dir = default_webui_dir()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "clawcode-openai-anthropic"})

    @app.get("/v1/models")
    def models():
        """
        List models visible to ClawCode.

        With header ``anthropic-version`` (any non-empty value): Anthropic-shaped JSON.
        Otherwise: OpenAI-shaped list.
        """
        rows = _clawcode_openai_models_rows()
        if wants_anthropic_models_list(request.headers):
            ids = [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]
            return jsonify(anthropic_models_list_payload(ids))
        return jsonify({"object": "list", "data": rows})

    def _max_steps_for_request(openai_body: dict) -> int:
        try:
            from config import get_clawcode_max_agent_steps

            default_cap = get_clawcode_max_agent_steps()
        except Exception:
            default_cap = 40
        ms = openai_body.get("max_agent_steps")
        if ms is not None and str(ms).strip() != "":
            try:
                n = int(ms)
                if 1 <= n <= 256:
                    return n
            except (TypeError, ValueError):
                pass
        return default_cap

    def _run_agent(openai_body: dict, *, private_mode: bool) -> tuple[dict, int]:
        max_steps = _max_steps_for_request(openai_body)

        def _cb(rec: dict) -> None:
            if rec.get("chiron_private"):
                return
            trace_append(rec)
            persist_clawcode_trace_to_db(rec)

        return run_clawcode_chat_completion(
            openai_body,
            webui_dir=webui_dir,
            max_steps=max_steps,
            trace_callback=_cb,
            private_mode=private_mode,
        )

    @app.post("/v1/chat/completions")
    def chat_completions():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": {"message": "JSON body required", "type": "invalid_request_error"}}), 400

        private_mode = _chiron_private_mode_from_request()
        want_stream = bool(body.get("stream"))

        if want_stream:
            _max = _max_steps_for_request(body)

            def _cb_stream(rec: dict) -> None:
                if rec.get("chiron_private"):
                    return
                trace_append(rec)
                persist_clawcode_trace_to_db(rec)

            def gen():
                yield from iter_clawcode_agent_sse(
                    body,
                    webui_dir=webui_dir,
                    max_steps=_max,
                    trace_callback=_cb_stream,
                    private_mode=private_mode,
                )

            return Response(
                gen(),
                mimetype="text/event-stream",
                status=200,
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        try:
            resp, code = _run_agent(body, private_mode=private_mode)
        except Exception as e:
            _LOG.exception("chat_completions failed: %s", e)
            return jsonify({"error": {"message": str(e), "type": "internal_error"}}), 500

        return jsonify(resp), code

    @app.post("/v1/messages")
    def anthropic_messages():
        raw = request.get_json(silent=True)
        if not isinstance(raw, dict):
            return (
                jsonify(
                    {
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "JSON body required",
                        },
                    }
                ),
                400,
            )

        stream = bool(raw.get("stream"))
        openai_body = anthropic_messages_request_to_openai_body(raw)
        openai_body["stream"] = False

        try:
            resp, code = _run_agent(openai_body)
        except Exception as e:
            _LOG.exception("anthropic_messages failed: %s", e)
            return (
                jsonify(
                    {
                        "type": "error",
                        "error": {"type": "internal_error", "message": str(e)},
                    }
                ),
                500,
            )

        if code != 200:
            if isinstance(resp, dict) and isinstance(resp.get("error"), dict):
                e = resp["error"]
                return (
                    jsonify(
                        {
                            "type": "error",
                            "error": {
                                "type": str(e.get("type", "api_error")),
                                "message": str(e.get("message", "")),
                            },
                        }
                    ),
                    code,
                )
            return jsonify(resp), code

        if not isinstance(resp, dict):
            return jsonify({"type": "error", "error": {"type": "api_error", "message": "invalid response"}}), 500

        stream_model = str(resp.get("model") or openai_body.get("model") or "")

        if stream:

            def gen():
                yield from anthropic_stream_from_openai_completion_dict(
                    resp, stream_model=stream_model
                )

            return Response(
                gen(),
                mimetype="text/event-stream",
                status=200,
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        return jsonify(openai_chat_completion_to_anthropic_message(resp))

    return app
