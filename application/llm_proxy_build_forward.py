"""Forward OpenAI chat to ClawCode for LLM Proxy builds with backend=claw."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests
from flask import Response, jsonify

from config import get_clawcode_host, get_clawcode_openai_port, get_server_host

_LOG = logging.getLogger(__name__)


def _last_user_query_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            return c
        if c is None:
            return ""
        try:
            return json.dumps(c, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(c)
    return ""


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
    POST to ClawCode; the forwarded JSON uses the build's concrete Ollama tag as ``model`` (required).
    ClawCode resolves the upstream model from that field (or from RAG/chat config if ``model`` were empty).
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
    forward["include_skill_tools"] = bool(build.get("skills_enabled", True))

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

    try:
        from infrastructure.database import get_logs_repository
        from infrastructure.database.session_manager import get_session_manager

        user_q = _last_user_query_from_messages(body.get("messages"))
        content_preview = ""
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    c0 = msg.get("content")
                    if isinstance(c0, str):
                        content_preview = c0[:500]

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        tt = usage.get("total_tokens")

        rag_meta = data.get("rag_metadata")
        rag_context_data = None
        if isinstance(rag_meta, dict):
            chunks = rag_meta.get("chunks_info") or []
            cc = rag_meta.get("chunks_count")
            if cc is None and isinstance(chunks, list):
                cc = len(chunks)
            rag_context_data = {
                "chunks_info": chunks if isinstance(chunks, list) else [],
                "max_score": rag_meta.get("max_score"),
                "chunks_count": int(cc or 0),
            }

        log_model = bid if bid else str(data.get("model") or ollama_tag)
        db_path = os.getenv("WEBUI_DB_PATH", "logs/webui.db")
        get_session_manager(db_path).get_or_create_session("proxy")
        logs_repo = get_logs_repository()
        logs_repo.add_log(
            session_id="proxy",
            level="INFO",
            message=f"Proxy request (claw): {user_q[:100]}...",
            source="proxy",
            metadata={
                "user_query": user_q[:500],
                "response_preview": content_preview,
                "model": log_model,
                "requested_model": (str(body.get("model") or "").strip() or log_model),
                "latency_ms": int(data.get("latency_ms") or latency_ms),
                "prompt_tokens": int(pt) if isinstance(pt, (int, float)) else 0,
                "completion_tokens": int(ct) if isinstance(ct, (int, float)) else 0,
                "total_tokens": int(tt) if isinstance(tt, (int, float)) else 0,
                "rag_context": rag_context_data,
                "proxy_backend": "claw",
                "claw_build_id": bid or None,
                "stream": bool(body.get("stream")),
                "is_autocomplete": False,
            },
        )
    except Exception as e:
        _LOG.warning("forward_claw_build_chat: failed to persist proxy log: %s", e)

    return jsonify(data), 200
