"""Forward OpenAI chat to ClawCode for LLM Proxy builds with backend=claw."""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from flask import Response, jsonify

from config import get_clawcode_host, get_clawcode_openai_port, get_server_host


def _claw_openai_base() -> str:
    env = (os.getenv("CLAWCODE_OPENAI_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    host = get_clawcode_host()
    port = get_clawcode_openai_port()
    if host in ("0.0.0.0", "::", ""):
        dh = get_server_host()
        if dh in ("0.0.0.0", "::", ""):
            dh = "127.0.0.1"
        host = dh
    return f"http://{host}:{port}".rstrip("/")


def forward_claw_build_chat(body: dict[str, Any], build: dict[str, Any]) -> Any:
    """
    POST to ClawCode agent; use the build's concrete Ollama tag as ``model`` (same as dumb builds),
    not ClawCode's logical model id — agent_runner resolves ``use_model`` from this request field.
    """
    ollama_tag = str(build.get("ollama_model") or "").strip()
    if not ollama_tag:
        return jsonify({"error": "claw build is missing ollama_model"}), 400

    base = _claw_openai_base()
    forward: dict[str, Any] = {
        "model": ollama_tag,
        "messages": body.get("messages") or [],
    }
    passthrough_keys = (
        "temperature",
        "top_p",
        "tools",
        "tool_choice",
        "stream",
        "merge_client_tools",
        "think",
    )
    for key in passthrough_keys:
        if key in body:
            forward[key] = body[key]

    if "temperature" not in forward and build.get("temperature") is not None:
        try:
            forward["temperature"] = float(build["temperature"])
        except (TypeError, ValueError):
            pass
    if "top_p" not in forward and build.get("top_p") is not None:
        try:
            forward["top_p"] = float(build["top_p"])
        except (TypeError, ValueError):
            pass
    if build.get("chat_think") and "think" not in forward:
        forward["think"] = True

    ms = build.get("max_agent_steps")
    if ms is not None:
        try:
            n = int(ms)
            if 1 <= n <= 256:
                forward["max_agent_steps"] = n
        except (TypeError, ValueError):
            pass

    # Build profile always controls whether ClawCode registers rag_query (ignore client override on this hop).
    forward["include_rag_query_tool"] = bool(build.get("rag_enabled", True))

    try:
        timeout_sec = float(os.getenv("CLAWCODE_CHAT_TIMEOUT_SEC", "600"))
    except (TypeError, ValueError):
        timeout_sec = 600.0

    start_time = time.time()
    try:
        resp = requests.post(
            f"{base}/v1/chat/completions",
            json=forward,
            timeout=(10.0, timeout_sec),
        )
    except requests.RequestException as e:
        return jsonify({"error": f"ClawCode unreachable at {base}: {e}"}), 502

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "text/event-stream" in content_type:
        # Pass through SSE
        def gen():
            for chunk in resp.iter_content(chunk_size=None):
                if chunk:
                    yield chunk

        return Response(
            gen(),
            status=resp.status_code,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "ClawCode returned non-JSON response"}), 502

    if resp.status_code >= 400:
        err = data.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or err)
        else:
            msg = str(err or resp.text or "ClawCode error")
        return jsonify({"error": msg}), 502

    latency_ms = int((time.time() - start_time) * 1000)
    if "latency_ms" not in data:
        data["latency_ms"] = latency_ms

    # Report build id to client (OpenAI model field)
    bid = str(build.get("id") or "").strip()
    if bid:
        data["model"] = bid

    include_rag_metadata = body.get("include_rag_metadata", True)
    if not include_rag_metadata:
        data.pop("rag_metadata", None)

    return jsonify(data), 200
