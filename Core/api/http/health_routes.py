"""Health and readiness routes for the host Flask app."""

from __future__ import annotations

from collections.abc import Callable

from flask import Flask, Response, jsonify

from infrastructure.stack_health import StackHealthResult


def register_health_routes(app: Flask, check_health: Callable[[], StackHealthResult]) -> None:
    """Register root-level health and readiness probes."""

    @app.route("/live", methods=["GET"])
    def live() -> Response:
        # Liveness probe: confirms the process is serving HTTP.
        return jsonify({"status": "ok"}), 200

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        result = check_health()
        return jsonify(result.to_json_dict(service="rag_proxy")), result.http_status

    @app.route("/ready", methods=["GET"])
    def ready() -> Response:
        result = check_health()
        return jsonify(result.to_json_dict(service="rag_proxy", probe="ready")), result.http_status


__all__ = ["register_health_routes"]
