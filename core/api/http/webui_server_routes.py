"""Server lifecycle routes for the WebUI blueprint."""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Blueprint, jsonify, request

_WEBUI_LOG = logging.getLogger("webui")


def _shutdown_werkzeug_server() -> None:
    shutdown = request.environ.get("werkzeug.server.shutdown")
    if callable(shutdown):
        shutdown()
        return
    os._exit(0)


def register_server_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/server/stop", methods=["POST"])
    def stop_server() -> Any:
        """Gracefully stop the local WebUI HTTP server (dev / local shutdown)."""
        try:
            _WEBUI_LOG.info("Received WebUI shutdown request")
            _shutdown_werkzeug_server()
            return jsonify({"status": "stopping"})
        except Exception as exc:
            error_log.error("webui_server_routes.stop_server", exc_info=True)
            return jsonify({"error": str(exc)}), 500


__all__ = ["register_server_routes"]
