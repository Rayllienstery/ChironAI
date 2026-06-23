"""Shared Ollama + Qdrant readiness checks for HTTP /health endpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests


@dataclass(frozen=True)
class StackHealthResult:
    """Result of dependency checks; use to_json_dict() for Flask jsonify."""

    overall: str
    components: dict[str, str]
    timestamp: str
    http_status: int

    def to_json_dict(self, **extra: Any) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.overall,
            "components": dict(self.components),
            "timestamp": self.timestamp,
        }
        out.update(extra)
        return out


def check_stack_health(
    *,
    timeout_seconds: float = 3.0,
    provider_health_component: Callable[[], str | None] | None = None,
) -> StackHealthResult:
    """
    Probe Ollama provider health (extension runtime) and Qdrant (/collections).
    Returns 200-style payload with http_status 200 or 503.
    """
    from config import get_qdrant_url

    components: dict[str, str] = {"ollama": "unknown", "qdrant": "unknown"}
    overall = "healthy"

    qdrant_url = get_qdrant_url().rstrip("/")

    components["ollama"] = (
        provider_health_component() if provider_health_component is not None else None
    ) or "unhealthy"
    if components["ollama"] != "healthy":
        overall = "unhealthy"

    try:
        resp = requests.get(f"{qdrant_url}/collections", timeout=timeout_seconds)
        components["qdrant"] = "healthy" if resp.ok else "unhealthy"
        if not resp.ok:
            overall = "unhealthy"
    except Exception:
        components["qdrant"] = "unhealthy"
        overall = "unhealthy"

    ts = datetime.now(timezone.utc).isoformat()
    code = 200 if overall == "healthy" else 503
    return StackHealthResult(
        overall=overall,
        components=components,
        timestamp=ts,
        http_status=code,
    )
