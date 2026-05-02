"""Derive Ollama base URL from configured /api/chat URL and forward common /api/* calls."""

from __future__ import annotations

from typing import Any

import requests
from flask import Response, jsonify, request, stream_with_context


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
    chat_full = get_configured_ollama_chat_url(wiring)
    base = ollama_api_base_from_chat_url(chat_full)
    url = f"{base}/api/{api_segment.lstrip('/')}"
    method = request.method.upper()

    if method == "GET":
        try:
            upstream = requests.get(url, params=request.args, timeout=120)
            upstream.raise_for_status()
        except requests.RequestException as e:
            return jsonify({"error": str(e)}), 502
        try:
            return jsonify(upstream.json())
        finally:
            upstream.close()

    body = request.get_json(force=True, silent=True)
    if body is None:
        body = {}
    stream = bool(stream_override if stream_override is not None else body.get("stream", False))

    try:
        if stream:
            upstream = requests.post(url, json=body, timeout=None, stream=True)
        else:
            upstream = requests.post(url, json=body, timeout=600, stream=False)
        upstream.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    if stream:

        def generate():
            try:
                for line in upstream.iter_lines(decode_unicode=True):
                    if line:
                        yield line + "\n"
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
