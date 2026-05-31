"""Pure request/trace parsing helpers for /v1/chat/completions."""

from __future__ import annotations

import os
from typing import Any


def truthy_body_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        n = int(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        n = default
    return max(256, n)


def non_empty_str(raw: object) -> str:
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            return s
        return ""
    if raw is None:
        return ""
    s = str(raw).strip()
    return s if s else ""


def resolve_trace_chain_id(
    *,
    client_request_id: object,
    proxy_trace_meta: dict[str, Any] | None,
) -> tuple[str, str]:
    """
    Resolve stable UI chain key for consecutive requests.

    Priority:
    1) explicit ``client_request_id`` from payload
    2) inbound request id propagated via ``_proxy_trace_meta``
    """
    client_id = non_empty_str(client_request_id)
    if client_id:
        return client_id, "client_request_id"

    meta = proxy_trace_meta if isinstance(proxy_trace_meta, dict) else {}
    for key in (
        "trace_chain_id",
        "chain_id",
        "responses_chain_id",
        "conversation_id",
        "thread_id",
        "session_id",
        "incoming_request_id",
        "x_trace_id",
        "x_request_id",
        "request_id",
        "trace_id",
    ):
        value = non_empty_str(meta.get(key))
        if value:
            return value, key
    return "", ""
