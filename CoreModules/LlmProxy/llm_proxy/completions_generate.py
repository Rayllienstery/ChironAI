"""POST /v1/completions backed by native Ollama POST /api/generate (e.g. Zed edit prediction)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import requests
from flask import Response, jsonify, request, stream_with_context

from llm_proxy.openai_text_completion_format import (
    legacy_completions_stream_line,
    non_stream_text_completion_response,
)
from llm_proxy.config import is_rag_logical_model_id
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.ollama_upstream import get_configured_ollama_chat_url, ollama_api_base_from_chat_url

_LOG = logging.getLogger("llm_proxy")


def _coerce_prompt(openai_body: dict[str, Any]) -> str:
    p = openai_body.get("prompt")
    if isinstance(p, str):
        return p
    if isinstance(p, list):
        return "".join(x for x in p if isinstance(x, str))
    return ""


def _map_done_reason_to_finish(dr: str | None) -> str | None:
    if not dr:
        return "stop"
    if dr == "length":
        return "length"
    if dr in ("stop", "load"):
        return "stop"
    return "stop"


def _resolve_ollama_model(w: LlmProxyWiring, requested: str) -> tuple[str | None, str | None]:
    """Return (ollama_tag, error_message)."""
    rt = w.runtime
    req = (requested or "").strip()
    if not req:
        return None, "model is required"
    if req == rt.autocomplete_model_logical_id:
        tag = w.get_autocomplete_ollama_model()
        if not tag:
            return None, (
                "LLM Proxy autocomplete is not configured: choose an Ollama model for autocomplete "
                "in WebUI (LLM Proxy → Autocomplete), or set LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL."
            )
        return tag, None
    if is_rag_logical_model_id(req, rt.rag_model_logical_id):
        try:
            repo = w.get_settings_repository()
            pm = (repo.get_app_setting("proxy_model") or "").strip()
            raw_ps = repo.get_app_setting("proxy_settings")
            if raw_ps:
                loaded = json.loads(raw_ps)
                if isinstance(loaded, dict) and loaded.get("model"):
                    pm = pm or str(loaded.get("model") or "").strip()
            if not pm or is_rag_logical_model_id(pm, rt.rag_model_logical_id):
                return None, (
                    "LLM Proxy is not configured: choose a concrete Ollama model in WebUI "
                    f"(LLM Proxy → Model Settings), not the logical id ({rt.rag_model_logical_id})."
                )
            return pm, None
        except Exception as e:
            _LOG.warning("completions_generate: resolve worker model: %s", e)
            return None, "Failed to read proxy model from settings"
    return req, None


def _openai_to_ollama_generate_body(openai: dict[str, Any], ollama_model: str, prompt: str) -> dict[str, Any]:
    raw_on = os.getenv("LLM_PROXY_COMPLETIONS_RAW", "true").strip().lower() not in ("0", "false", "no")

    body: dict[str, Any] = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    if raw_on:
        body["raw"] = True

    suf = openai.get("suffix")
    if isinstance(suf, str) and suf:
        body["suffix"] = suf

    opts: dict[str, Any] = {}
    mt = openai.get("max_tokens")
    if mt is None:
        mt = openai.get("max_completion_tokens")
    if mt is not None:
        try:
            opts["num_predict"] = int(mt)
        except (TypeError, ValueError):
            pass
    if openai.get("temperature") is not None:
        try:
            opts["temperature"] = float(openai["temperature"])
        except (TypeError, ValueError):
            pass
    if openai.get("top_p") is not None:
        try:
            opts["top_p"] = float(openai["top_p"])
        except (TypeError, ValueError):
            pass
    st = openai.get("stop")
    if isinstance(st, str) and st:
        opts["stop"] = [st]
    elif isinstance(st, list):
        opts["stop"] = [str(x) for x in st if x is not None and str(x)]

    if opts:
        body["options"] = opts

    return body


def run_legacy_completions_via_ollama_generate(
    w: LlmProxyWiring,
) -> Response | tuple[Response, int]:
    """
    OpenAI-compatible ``/v1/completions`` implemented as Ollama ``/api/generate``.
    No RAG, no WebUI prompt template, no web supplement — same contract as pointing Zed at Ollama.
    """
    try:
        openai_body = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        w.log_webui_error("rag_routes.completions_generate", e, {"stage": "parse_body"})
        return jsonify({"error": "Invalid JSON"}), 400

    req_model = str(openai_body.get("model") or "").strip()
    ollama_tag, err = _resolve_ollama_model(w, req_model)
    if err or not ollama_tag:
        return jsonify({"error": err or "model resolution failed"}), 400

    prompt = _coerce_prompt(openai_body)
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    ollama_body = _openai_to_ollama_generate_body(openai_body, ollama_tag, prompt)
    client_stream = bool(openai_body.get("stream", False))

    chat_url = get_configured_ollama_chat_url(w)
    base = ollama_api_base_from_chat_url(chat_url)
    url = f"{base}/api/generate"

    try:
        upstream = requests.post(url, json=ollama_body, timeout=600, stream=False)
        upstream.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    try:
        data = upstream.json()
    finally:
        upstream.close()

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid response from Ollama"}), 502
    if data.get("error"):
        return jsonify({"error": str(data.get("error"))}), 502

    text = data.get("response") if isinstance(data.get("response"), str) else ""
    dr = data.get("done_reason")
    finish = _map_done_reason_to_finish(dr if isinstance(dr, str) else None)

    try:
        pt = int(data.get("prompt_eval_count") or 0)
        ct = int(data.get("eval_count") or 0)
    except (TypeError, ValueError):
        pt, ct = 0, 0
    if pt == 0 and ct == 0:
        pt = max(1, len(prompt) // 4)
        ct = max(1, len(text) // 4 if text else 1)

    if client_stream:

        def generate():
            oid = f"cmpl-{uuid.uuid4().hex[:24]}"
            if text:
                yield legacy_completions_stream_line(oid, req_model, text, None)
            yield legacy_completions_stream_line(oid, req_model, "", finish)
            yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    rd = non_stream_text_completion_response(
        use_model=req_model,
        text=text,
        finish_reason=finish,
        prompt_tokens_approx=pt,
        completion_tokens_approx=ct,
    )
    return jsonify(rd)


__all__ = ["run_legacy_completions_via_ollama_generate"]
