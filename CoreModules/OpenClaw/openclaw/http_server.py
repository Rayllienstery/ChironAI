"""Flask app: OpenAI-compatible /v1/chat/completions and Anthropic /v1/messages for OpenClaw agent."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Monorepo: allow ``import llm_proxy`` without a separate ``pip install -e`` when this path exists.
_llm_proxy_src = Path(__file__).resolve().parents[3] / "CoreModules" / "LlmProxy"
if _llm_proxy_src.is_dir():
    _lp = str(_llm_proxy_src)
    if _lp not in sys.path:
        sys.path.insert(0, _lp)

from flask import Flask, Response, jsonify, request

from llm_proxy.anthropic_compat import (
    anthropic_messages_request_to_openai_body,
    anthropic_models_list_payload,
    anthropic_stream_from_openai_completion_dict,
    openai_chat_completion_to_anthropic_message,
    wants_anthropic_models_list,
)

from openclaw.agent_runner import run_openclaw_chat_completion
from openclaw.trace_journal import persist_openclaw_trace_to_db
from openclaw.trace_store import append as trace_append

_LOG = logging.getLogger("openclaw.http")


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_webui_dir() -> str:
    env = os.environ.get("CHIRONAI_WEBUI_DIR", "").strip()
    if env:
        return env
    return str(project_root() / "WebUI")


def _openclaw_openai_models_rows() -> tuple[str, list[dict[str, object]]]:
    """
    Return (logical_model_id, data_rows) matching the OpenAI /v1/models list shape
    (without the outer wrapper).
    """
    logical = "Claw-Agent"
    data: list[dict[str, object]] = []
    try:
        from config import (
            get_ollama_base_url,
            get_ollama_chat_model,
            get_openclaw_logical_model_id,
        )
        from infrastructure.ollama.cli_runner import invoke_tags

        logical = get_openclaw_logical_model_id()
        base_url = get_ollama_base_url()
        tags = invoke_tags(base_url=base_url, timeout=5.0)
        models = tags.get("models") or []
        seen: set[str] = set()
        for m in models:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or m.get("model") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            data.append({"id": name, "object": "model", "owned_by": "ollama"})
        cfg_model = get_ollama_chat_model()
        if cfg_model and cfg_model not in seen:
            data.insert(0, {"id": cfg_model, "object": "model", "owned_by": "ollama"})
    except Exception:
        try:
            from config import get_ollama_chat_model

            cfg_model = get_ollama_chat_model()
        except Exception:
            cfg_model = "unknown"
        data = [{"id": cfg_model, "object": "model", "owned_by": "ollama"}]
    return logical, data


def create_openclaw_flask_app() -> Flask:
    app = Flask(__name__)
    webui_dir = default_webui_dir()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "openclaw-openai-anthropic"})

    @app.get("/v1/models")
    def models():
        """
        List models visible to OpenClaw.

        With header ``anthropic-version`` (any non-empty value): Anthropic-shaped JSON.
        Otherwise: OpenAI-shaped list.
        """
        logical, rows = _openclaw_openai_models_rows()
        if wants_anthropic_models_list(request.headers):
            ids = [logical] + [str(r.get("id")) for r in rows if isinstance(r, dict) and r.get("id")]
            return jsonify(anthropic_models_list_payload(ids))
        return jsonify(
            {
                "object": "list",
                "data": [{"id": logical, "object": "model", "owned_by": "openclaw"}] + rows,
            }
        )

    def _run_agent(openai_body: dict) -> tuple[dict, int]:
        try:
            from config import get_openclaw_logical_model_id, get_openclaw_max_agent_steps

            max_steps = get_openclaw_max_agent_steps()
            logical_id = get_openclaw_logical_model_id()
        except Exception:
            max_steps, logical_id = 40, "Claw-Agent"

        def _cb(rec: dict) -> None:
            trace_append(rec)
            persist_openclaw_trace_to_db(rec)

        return run_openclaw_chat_completion(
            openai_body,
            webui_dir=webui_dir,
            max_steps=max_steps,
            logical_model_id=logical_id,
            trace_callback=_cb,
        )

    @app.post("/v1/chat/completions")
    def chat_completions():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": {"message": "JSON body required", "type": "invalid_request_error"}}), 400

        try:
            resp, code = _run_agent(body)
            return jsonify(resp), code
        except Exception as e:
            _LOG.exception("chat_completions failed: %s", e)
            return jsonify({"error": {"message": str(e), "type": "internal_error"}}), 500

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
