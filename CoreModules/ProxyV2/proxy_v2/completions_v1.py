"""POST /v1/completions — OpenAI legacy completions via Ollama /api/generate."""

from __future__ import annotations

import json
import os
import traceback
import uuid
from copy import deepcopy
from typing import Any

import requests
from flask import Response, jsonify, request, stream_with_context

from proxy_v2.contracts import ProxyV2Wiring
from proxy_v2.ollama_url import ollama_api_base_from_chat_url
from proxy_v2.text_completion_format import legacy_completions_stream_line, non_stream_text_completion_response
from proxy_v2.trace_store import append_stream_line, new_trace, phase, record_error, set_current_trace


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


def _openai_to_ollama_generate_body(openai: dict[str, Any], ollama_model: str, prompt: str) -> dict[str, Any]:
    stream = bool(openai.get("stream", False))
    raw_on = os.getenv("LLM_PROXY_COMPLETIONS_RAW", "true").strip().lower() not in ("0", "false", "no")
    body: dict[str, Any] = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": stream,
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


def run_v1_completions(w: ProxyV2Wiring) -> Response | tuple[Response, int]:
    tid = f"v2-{uuid.uuid4().hex[:12]}"
    tr = new_trace(tid)
    tr["request"]["path"] = request.path
    set_current_trace(tr)
    try:
        openai_body = request.get_json(force=True, silent=True) or {}
    except Exception as e:
        record_error(tr, str(e), traceback.format_exc())
        set_current_trace(tr)
        return jsonify({"error": "Invalid JSON"}), 400

    pinned = (w.get_pinned_model() or "").strip()
    req_model = str(openai_body.get("model") or "").strip()
    ollama_tag = pinned or req_model
    tr["request"]["model_requested"] = req_model or openai_body.get("model")
    tr["request"]["model_resolved"] = ollama_tag

    if not ollama_tag:
        return jsonify(
            {"error": "model is required (or set Proxy V2 pinned model in WebUI)"},
        ), 400

    prompt = _coerce_prompt(openai_body)
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    tr["request"]["openai_body"] = deepcopy(openai_body)

    ollama_body = _openai_to_ollama_generate_body(openai_body, ollama_tag, prompt)
    chat_url = w.get_ollama_chat_url()
    base = ollama_api_base_from_chat_url(chat_url)
    url = f"{base}/api/generate"
    tr["upstream"]["url"] = url
    tr["upstream"]["body"] = deepcopy(ollama_body)
    tr["upstream"]["body_summary"] = {"model": ollama_tag, "stream": bool(ollama_body.get("stream"))}
    set_current_trace(tr)
    stream = bool(ollama_body.get("stream", False))
    phase(tr, "upstream_post", stream=stream)

    try:
        if stream:
            upstream = requests.post(url, json=ollama_body, timeout=600, stream=True)
            upstream.raise_for_status()
        else:
            upstream = requests.post(url, json=ollama_body, timeout=600, stream=False)
            upstream.raise_for_status()
    except requests.RequestException as e:
        record_error(tr, str(e), traceback.format_exc())
        set_current_trace(tr)
        return jsonify({"error": str(e)}), 502

    if stream:

        def generate():
            oid = f"cmpl-{uuid.uuid4().hex[:24]}"
            saw_done = False
            content_sent = False
            try:
                for line in upstream.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    append_stream_line(tr, line)
                    set_current_trace(tr)
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    err_obj = obj.get("error")
                    if err_obj:
                        yield f"data: {json.dumps({'error': err_obj if isinstance(err_obj, str) else str(err_obj)})}\n\n"
                        break
                    piece = obj.get("response")
                    if isinstance(piece, str) and piece:
                        content_sent = True
                        yield legacy_completions_stream_line(oid, req_model or ollama_tag, piece, None)
                    if obj.get("done"):
                        saw_done = True
                        dr = obj.get("done_reason")
                        fr = _map_done_reason_to_finish(dr if isinstance(dr, str) else None)
                        # Only yield finish chunk if we actually sent content
                        if content_sent:
                            yield legacy_completions_stream_line(oid, req_model or ollama_tag, "", fr)
                        break
            finally:
                upstream.close()
            if not saw_done and content_sent:
                yield legacy_completions_stream_line(oid, req_model or ollama_tag, "", "stop")
            yield "data: [DONE]\n\n"
            phase(tr, "stream_complete")
            set_current_trace(tr)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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

    rd = non_stream_text_completion_response(
        use_model=req_model or ollama_tag,
        text=text,
        finish_reason=finish,
        prompt_tokens_approx=pt,
        completion_tokens_approx=ct,
    )
    phase(tr, "complete")
    set_current_trace(tr)
    return jsonify(rd)


__all__ = ["run_v1_completions"]
