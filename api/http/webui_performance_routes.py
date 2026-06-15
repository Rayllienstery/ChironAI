"""WebUI performance diagnostics routes."""

from __future__ import annotations

from typing import Any

from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request

from api.http.startup_timing import get_startup_report, record_browser_timing


def register_performance_routes(bp: Blueprint) -> None:
    @bp.route("/performance/startup", methods=["GET"])
    def get_startup_performance() -> Any:
        """Return startup timing report for all instrumented phases.

        Includes Python-server phases recorded during process startup and any
        browser timing submitted via POST /performance/browser-timing.
        """
        try:
            return jsonify(get_startup_report())
        except Exception as e:
            return _error_response(e)

    @bp.route("/performance/browser-timing", methods=["POST"])
    def post_browser_timing() -> Any:
        """Accept browser Navigation Timing payload from the frontend.

        The frontend posts ``window.performance.timing`` plus React lifecycle
        milestones so they can be merged into the startup report and shown
        alongside server-side phases.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            if not isinstance(body, dict):
                return _error_response("body must be a JSON object", 400)
            record_browser_timing(body)
            return jsonify({"ok": True})
        except Exception as e:
            return _error_response(e)


__all__ = ["register_performance_routes"]
