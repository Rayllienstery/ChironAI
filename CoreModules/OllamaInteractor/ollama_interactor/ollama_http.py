"""Low-level HTTP calls to Ollama. Used only by this package's CLI."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests


def get_tags(base_url: str, timeout: float = 30.0) -> dict[str, Any]:
    base = base_url.rstrip("/")
    url = f"{base}/api/tags"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def ping(base_url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Lightweight reachability check (GET /api/tags)."""
    base = base_url.rstrip("/")
    url = f"{base}/api/tags"
    resp = requests.get(url, timeout=timeout)
    ok = resp.status_code == 200
    return {"ok": ok, "status_code": resp.status_code}


def post_json(
    url: str,
    body: dict[str, Any],
    *,
    timeout: float = 600.0,
    stream: bool = False,
) -> requests.Response:
    return requests.post(url, json=body, timeout=timeout, stream=stream)


def post_json_return_dict(url: str, body: dict[str, Any], timeout: float = 600.0) -> dict[str, Any]:
    resp = post_json(url, body, timeout=timeout, stream=False)
    resp.raise_for_status()
    return resp.json()


def stream_chat_lines(url: str, body: dict[str, Any], timeout: float = 600.0) -> Iterator[str]:
    """POST /api/chat with stream=True; yield raw NDJSON lines (without trailing newline)."""
    resp = post_json(url, body, timeout=timeout, stream=True)
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if line:
            yield line


def format_http_error(exc: requests.exceptions.HTTPError) -> dict[str, Any]:
    r = exc.response
    out: dict[str, Any] = {
        "error": str(exc),
        "status_code": r.status_code if r is not None else None,
    }
    if r is not None and r.text:
        try:
            out["body"] = r.json()
        except (ValueError, json.JSONDecodeError):
            out["body_text"] = r.text[:2000]
    return out
