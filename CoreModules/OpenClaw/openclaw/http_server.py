"""Flask app: OpenAI-compatible /v1/chat/completions for OpenClaw agent."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request

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


def create_openclaw_flask_app() -> Flask:
    app = Flask(__name__)
    webui_dir = default_webui_dir()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "openclaw-openai"})

    @app.get("/v1/models")
    def models():
        """
        List models visible to OpenClaw.

        - Always includes the logical OpenClaw agent id (e.g. \"Claw-Agent\").
        - Dynamically lists Ollama models from /api/tags where possible.
        """
        logical = "Claw-Agent"
        data = []
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
            # Ensure at least the configured chat model is present
            cfg_model = get_ollama_chat_model()
            if cfg_model and cfg_model not in seen:
                data.insert(0, {"id": cfg_model, "object": "model", "owned_by": "ollama"})
        except Exception:
            # Fallback: only configured chat model, no dynamic Ollama list
            try:
                from config import get_ollama_chat_model

                cfg_model = get_ollama_chat_model()
            except Exception:
                cfg_model = "unknown"
            data = [{"id": cfg_model, "object": "model", "owned_by": "ollama"}]
        # Always prepend logical OpenClaw agent id
        return jsonify(
            {
                "object": "list",
                "data": [{"id": logical, "object": "model", "owned_by": "openclaw"}] + data,
            }
        )

    @app.post("/v1/chat/completions")
    def chat_completions():
        try:
            from config import get_openclaw_logical_model_id, get_openclaw_max_agent_steps

            max_steps = get_openclaw_max_agent_steps()
            logical_id = get_openclaw_logical_model_id()
        except Exception:
            max_steps, logical_id = 40, "Claw-Agent"

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": {"message": "JSON body required", "type": "invalid_request_error"}}), 400

        def _cb(rec: dict) -> None:
            trace_append(rec)
            persist_openclaw_trace_to_db(rec)

        try:
            resp, code = run_openclaw_chat_completion(
                body,
                webui_dir=webui_dir,
                max_steps=max_steps,
                logical_model_id=logical_id,
                trace_callback=_cb,
            )
            return jsonify(resp), code
        except Exception as e:
            _LOG.exception("chat_completions failed: %s", e)
            return jsonify({"error": {"message": str(e), "type": "internal_error"}}), 500

    return app
