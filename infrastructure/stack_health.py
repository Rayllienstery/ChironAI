"""Shared Ollama + Qdrant readiness checks for HTTP /health endpoints."""

from __future__ import annotations

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


def _provider_health_component() -> str | None:
    try:
        from flask import current_app, has_app_context
    except Exception:
        return None
    if not has_app_context():
        return None

    from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service

    svc = get_extensions_service(current_app)
    runtime = get_extensions_runtime(current_app, svc)
    if svc is None or runtime is None:
        return None

    try:
        rows = svc.provider_rows(runtime)
    except Exception:
        return "unhealthy"

    for row in rows or []:
        if str(row.get("provider_id") or "").strip() != "ollama":
            continue
        health = row.get("health") if isinstance(row.get("health"), dict) else {}
        return "healthy" if bool(health.get("ok")) else "unhealthy"
    return "unhealthy"


def _legacy_ollama_health_component(*, timeout_seconds: float) -> str:
    from config import get_ollama_base_url

    ollama_base = get_ollama_base_url().rstrip("/")
    try:
        resp = requests.get(f"{ollama_base}/api/tags", timeout=timeout_seconds)
        return "healthy" if resp.ok else "unhealthy"
    except Exception:
        return "unhealthy"


def check_stack_health(*, timeout_seconds: float = 3.0) -> StackHealthResult:
    """
    Probe Ollama provider health and Qdrant (/collections).
    If the extension runtime is not ready during startup, temporarily fall back
    to the legacy Ollama /api/tags probe.
    Returns 200-style payload with http_status 200 or 503.
    """
    from config import get_qdrant_url

    components: dict[str, str] = {"ollama": "unknown", "qdrant": "unknown"}
    overall = "healthy"

    qdrant_url = get_qdrant_url().rstrip("/")

    components["ollama"] = _provider_health_component() or _legacy_ollama_health_component(
        timeout_seconds=timeout_seconds
    )
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
