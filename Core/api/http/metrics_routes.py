"""Prometheus metrics and request observability middleware."""

from __future__ import annotations

import time
from typing import Any

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

from core.shared.correlation import resolve_correlation_id
from infrastructure.metrics import histogram as record_histogram
from infrastructure.metrics import increment as record_increment


def _endpoint_label() -> str:
    endpoint = str(request.endpoint or "").strip()
    if endpoint:
        return endpoint
    return request.path or "unknown"


def register_metrics_routes(app: Flask) -> None:
    """Register `/metrics` and collect HTTP request counters/latency."""

    registry = CollectorRegistry()
    request_counter = Counter(
        "chironai_http_requests_total",
        "HTTP requests handled by ChironAI.",
        ("method", "endpoint", "status"),
        registry=registry,
    )
    request_latency = Histogram(
        "chironai_http_request_duration_seconds",
        "HTTP request latency in seconds.",
        ("method", "endpoint"),
        registry=registry,
    )
    Histogram(
        "chironai_rag_pipeline_duration_seconds",
        "RAG pipeline stage latency in seconds.",
        ("stage",),
        registry=registry,
    )
    Counter(
        "chironai_http_errors_total",
        "HTTP responses with status code >= 500.",
        ("method", "endpoint", "status"),
        registry=registry,
    )
    app.extensions["prometheus_registry"] = registry

    @app.before_request
    def _metrics_before_request() -> None:
        g.request_started_at = time.perf_counter()
        g.request_id = resolve_correlation_id()

    @app.after_request
    def _metrics_after_request(response: Any) -> Any:
        started = float(getattr(g, "request_started_at", time.perf_counter()))
        duration = max(time.perf_counter() - started, 0.0)
        endpoint = _endpoint_label()
        method = request.method
        status = str(getattr(response, "status_code", 0) or 0)
        request_counter.labels(method=method, endpoint=endpoint, status=status).inc()
        request_latency.labels(method=method, endpoint=endpoint).observe(duration)
        record_increment("http_requests_total", tags={"method": method, "endpoint": endpoint, "status": status})
        record_histogram("http_request_duration_seconds", duration, tags={"method": method, "endpoint": endpoint})
        response.headers.setdefault("X-Request-Id", str(getattr(g, "request_id", "")))
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


__all__ = ["register_metrics_routes"]
