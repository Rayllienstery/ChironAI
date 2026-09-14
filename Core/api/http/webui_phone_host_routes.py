"""Compact phone-host status for iPhone Shortcuts."""

from __future__ import annotations

from typing import Any

from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request

from api.http.proxy_status import get_proxy_status_label
from api.http.proxy_trace import get_active_traces
from api.http.webui_trusted_client import check_phone_status_access
from application.host_memory import collect_gpu_snapshot
from application.phone_host_scripts import list_phone_host_scripts, set_phone_host_script_enabled
from application.phone_host_status import build_phone_host_status
from config.env import get_phone_status_gpu_busy_pct
from infrastructure.database import get_settings_repository


def _scripts_payload(settings_repo: Any | None = None) -> dict[str, Any]:
    repo = settings_repo
    if repo is None:
        try:
            repo = get_settings_repository()
        except Exception:
            repo = None
    return {"scripts": list_phone_host_scripts(repo)}


def register_phone_host_routes(bp: Blueprint) -> None:
    @bp.route("/host/phone-status", methods=["GET"])
    def get_host_phone_status() -> Any:
        """Return compact PC/Chiron generation status for SSH or tokenized LAN access."""
        try:
            denied = check_phone_status_access(request)
            if denied is not None:
                return denied
            gpu = None
            try:
                gpu = collect_gpu_snapshot()
            except Exception:
                gpu = None
            payload = build_phone_host_status(
                get_active_traces(),
                gpu,
                proxy_status=get_proxy_status_label(),
                gpu_busy_pct=get_phone_status_gpu_busy_pct(),
            )
            return jsonify(payload)
        except Exception as e:
            return _error_response(e)

    @bp.route("/host/phone-scripts", methods=["GET"])
    def get_host_phone_scripts() -> Any:
        """List iPhone phone-host scripts and whether each is enabled."""
        try:
            return jsonify(_scripts_payload())
        except Exception as e:
            return _error_response(e)

    @bp.route("/host/phone-scripts/<script_id>", methods=["PUT"])
    def put_host_phone_script(script_id: str) -> Any:
        """Enable or disable one phone-host script from CoreUI."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            if not isinstance(body, dict) or "enabled" not in body:
                return _error_response("body must include boolean enabled", 400)
            enabled = body.get("enabled")
            if not isinstance(enabled, bool):
                return _error_response("enabled must be a boolean", 400)
            try:
                repo = get_settings_repository()
            except Exception:
                repo = None
            scripts = set_phone_host_script_enabled(script_id, enabled, repo)
            return jsonify({"scripts": scripts})
        except KeyError:
            return _error_response("unknown phone-host script", 404)
        except Exception as e:
            return _error_response(e)


__all__ = ["register_phone_host_routes"]
