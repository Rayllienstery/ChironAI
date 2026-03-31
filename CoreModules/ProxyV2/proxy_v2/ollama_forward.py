"""Transparent Ollama /api/* forward with trace hooks."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import traceback
import uuid
from copy import deepcopy
from typing import Any

import requests
from flask import Response, jsonify, request, stream_with_context

from proxy_v2.contracts import ProxyV2Wiring
from proxy_v2.ollama_url import ollama_api_base_from_chat_url
from proxy_v2.trace_store import append_stream_line, new_trace, phase, record_error, set_current_trace


def _apply_pinned_model(body: dict[str, Any], pinned: str, trace: dict[str, Any]) -> dict[str, Any]:
    logger.debug(f"Applying pinned model: {pinned}")
    out = deepcopy(body) if body else {}
    req_model = out.get("model")
    trace["request"]["model_requested"] = req_model
    if pinned.strip():
        out["model"] = pinned.strip()
    trace["request"]["model_resolved"] = out.get("model")
    logger.debug(f"Model resolved to: {out.get('model')}")
    return out


def forward_ollama_segment(
    w: ProxyV2Wiring,
    api_segment: str,
    *,
    stream_override: bool | None = None,
) -> Response | tuple[Response, int]:
    tid = f"v2-{uuid.uuid4().hex[:12]}"
    tr = new_trace(tid)
    tr["request"]["path"] = request.path
    tr["request"]["method"] = request.method
    set_current_trace(tr)
    chat_full = w.get_ollama_chat_url()
    base = ollama_api_base_from_chat_url(chat_full)
    url = f"{base}/api/{api_segment.lstrip('/')}"
    pinned = (w.get_pinned_model() or "").strip()
    method = request.method.upper()

    try:
        logger.debug(f"Forwarding to Ollama segment: {api_segment}")
        phase(tr, "route", segment=api_segment, upstream_base=base)
        tr["upstream"]["url"] = url

        if method == "GET":
            try:
                upstream = requests.get(url, params=request.args, timeout=120)
                upstream.raise_for_status()
            except requests.RequestException as e:
                record_error(tr, str(e), traceback.format_exc())
                set_current_trace(tr)
                return jsonify({"error": str(e)}), 502
            try:
                data = upstream.json()
                phase(tr, "upstream_done", status=upstream.status_code)
                set_current_trace(tr)
                return jsonify(data)
            finally:
                upstream.close()

        body_in = request.get_json(force=True, silent=True)
        if body_in is None:
            body_in = {}
        if not isinstance(body_in, dict):
            return jsonify({"error": "JSON object body required"}), 400

        body = _apply_pinned_model(body_in, pinned, tr)
        logger.debug(f"Forwarding body to Ollama: {body}")
        stream = bool(stream_override if stream_override is not None else body.get("stream", False))
        tr["upstream"]["body"] = body
        phase(tr, "upstream_post", stream=stream)

        try:
            logger.debug(f"Sending request to Ollama (stream={stream})")
            if stream:
                upstream = requests.post(url, json=body, timeout=600, stream=True)
            else:
                upstream = requests.post(url, json=body, timeout=600, stream=False)
            upstream.raise_for_status()
            logger.debug(f"Ollama response status: {upstream.status_code}")
        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            record_error(tr, str(e), traceback.format_exc())
            set_current_trace(tr)
            return jsonify({"error": str(e)}), 502

        if stream:

            def generate():
                try:
                    for line in upstream.iter_lines(decode_unicode=True):
                        if line:
                            logger.debug(f"Ollama stream line: {line}")
                            append_stream_line(tr, line)
                            set_current_trace(tr)
                            yield line + "\n"
                finally:
                    upstream.close()
                    logger.debug("Ollama stream closed")
                    phase(tr, "stream_complete")
                    set_current_trace(tr)

            return Response(
                stream_with_context(generate()),
                mimetype=upstream.headers.get("Content-Type") or "application/x-ndjson",
            )

        try:
            js = upstream.json()
            phase(tr, "upstream_done", status=upstream.status_code)
            set_current_trace(tr)
            return jsonify(js)
        finally:
            upstream.close()
    except Exception as e:
        record_error(tr, str(e), traceback.format_exc())
        set_current_trace(tr)
        return jsonify({"error": str(e)}), 500


__all__ = ["forward_ollama_segment"]
