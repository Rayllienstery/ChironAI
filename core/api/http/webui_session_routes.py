"""Session routes for the WebUI blueprint."""

from __future__ import annotations

from typing import Any

from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request

from infrastructure.database import get_session_manager


def register_session_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/sessions", methods=["GET"])
    def get_sessions() -> Any:
        """Get or create a session."""
        try:
            session_id = request.args.get("session_id")
            session_manager = get_session_manager()
            session = session_manager.get_or_create_session(session_id)
            return jsonify(session)
        except Exception as e:
            error_log.error("webui_session_routes.get_sessions", exc_info=True)
            return _error_response(e)


__all__ = ["register_session_routes"]
