"""Derive Ollama base URL from configured /api/chat URL and forward common /api/* calls."""

from __future__ import annotations

import json
from typing import Any

import requests
from flask import Response, jsonify, request, stream_with_context
from llm_interactor.contracts import LLMRequest


def ollama_api_base_from_chat_url(chat_url: str) -> str:
    """``http://host:11434/api/chat`` -> ``http://host:11434``."""
    u = (chat_url or "").rstrip("/")
    if u.endswith("/api/chat"):
        return u[: -len("/api/chat")]
    return u


def get_configured_ollama_chat_url(wiring: Any) -> str:
    chat_client = getattr(wiring.base, "chat_client", None)
    url = getattr(chat_client, "_url", None) if chat_client is not None else None
    if url:
        return str(url)
    try:
        from config import get_ollama_chat_url

        return str(get_ollama_chat_url())
    except ImportError:
        return "http://localhost:11434/api/chat"


def _ollama_runtime(wiring: Any) -> Any | None:
    runtime = getattr(wiring, "llm_runtime", None)
    registry = getattr(runtime, "registry", None)
    get_provider = getattr(registry, "get", None)
    if runtime is None or not callable(get_provider):
        return None
    try:
        return runtime if get_provider("ollama") is not None else None
    except Exception:
        return None


def _ndjson_line_text(line: Any) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="replace")
    return str(line)


def _forward_ollama_api_via_runtime(
    wiring: Any,
    api_segment: str,
    *,
    method: str,
    body: dict[str, Any],
    params: dict[str, Any],
    headers: dict[str, str],
    stream: bool,
) -> Response | tuple[Response, int] | None:
    runtime = _ollama_runtime(wiring)
    if runtime is None:
        return None

    model = str(body.get("model") or body.get("name") or "ollama-compat").strip() or "ollama-compat"
    metadata = {
        "api_segment": api_segment,
        "method": method,
        "params": params,
        "headers": headers,
    }
    try:
        if stream:
            events = runtime.stream_invoke(
                LLMRequest(
                    provider_id="ollama",
                    model=model,
                    operation="raw_ollama",
                    body=body,
                    stream=True,
                    metadata={**metadata, "read_timeout": 86400.0},
                )
            )
            first = next(events, None)
            if first is not None and first.type == "error":
                return jsonify({"error": str(first.data)}), 502

            def generate():
                if first is not None and first.type == "raw_line":
                    yield _ndjson_line_text(first.data) + "\n"
                for event in events:
                    if event.type == "raw_line":
                        yield _ndjson_line_text(event.data) + "\n"
                    elif event.type == "error":
                        yield json.dumps({"error": str(event.data)}) + "\n"

            return Response(stream_with_context(generate()), mimetype="application/x-ndjson")

        response = runtime.invoke(
            LLMRequest(
                provider_id="ollama",
                model=model,
                operation="raw_ollama",
                body=body,
                metadata={**metadata, "timeout": 120.0 if method == "GET" else 600.0},
            )
        )
        return jsonify(response.raw if isinstance(response.raw, dict) else {})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def forward_ollama_api(
    wiring: Any,
    api_segment: str,
    *,
    stream_override: bool | None = None,
) -> Response | tuple[Response, int]:
    """
    Proxy to upstream Ollama ``{base}/api/{api_segment}``.

    ``api_segment`` is the path after ``/api/`` (e.g. ``tags``, ``show``, ``chat``).
    """
    hdrs: dict[str, str] = {}
    auth_in = str(request.headers.get("Authorization") or "").strip()
    if auth_in:
        hdrs["Authorization"] = auth_in

    chat_full = get_configured_ollama_chat_url(wiring)
    base = ollama_api_base_from_chat_url(chat_full)
    url = f"{base}/api/{api_segment.lstrip('/')}"
    method = request.method.upper()
    body = request.get_json(force=True, silent=True) if method != "GET" else {}
    if body is None:
        body = {}
    stream = bool(stream_override if stream_override is not None else body.get("stream", False))
    runtime_response = _forward_ollama_api_via_runtime(
        wiring,
        api_segment,
        method=method,
        body=dict(body or {}),
        params=dict(request.args or {}),
        headers=hdrs,
        stream=stream,
    )
    if runtime_response is not None:
        return runtime_response

    if method == "GET":
        try:
            upstream = requests.get(url, params=request.args, timeout=120, headers=hdrs or None)
            upstream.raise_for_status()
        except requests.RequestException as e:
            return jsonify({"error": str(e)}), 502
        try:
            return jsonify(upstream.json())
        finally:
            upstream.close()

    try:
        if stream:
            upstream = requests.post(url, json=body, timeout=None, stream=True, headers=hdrs or None)
        else:
            upstream = requests.post(url, json=body, timeout=600, stream=False, headers=hdrs or None)
        upstream.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    if stream:

        def generate():
            try:
                for line in upstream.iter_lines(decode_unicode=True):
                    if line:
                        yield _ndjson_line_text(line) + "\n"
            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            mimetype=upstream.headers.get("Content-Type") or "application/x-ndjson",
        )
    try:
        return jsonify(upstream.json())
    finally:
        upstream.close()


__all__ = [
    "forward_ollama_api",
    "get_configured_ollama_chat_url",
    "ollama_api_base_from_chat_url",
]
