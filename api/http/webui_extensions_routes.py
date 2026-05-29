"""Extension-management routes for WebUI."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file

from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service


def _get_extensions_service() -> Any:
    return get_extensions_service(current_app)


def _get_extensions_runtime(svc: Any) -> Any:
    return get_extensions_runtime(current_app, svc)


def _extension_error(message: str, code: str, status: int) -> Any:
    return jsonify({"error": message, "code": code}), status


def register_extension_routes(
    bp: Blueprint,
    *,
    error_log: Any,
) -> None:
    @bp.route("/extensions/registry", methods=["GET"])
    def get_extensions_registry() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"available": False, "registry": [], "registry_url": None}), 200
            if request.args.get("refresh") == "1":
                svc.invalidate_registry_cache()
            diagnostics = svc.registry_diagnostics()
            return jsonify(
                {
                    "available": True,
                    "registry": svc.registry_entries(),
                    "registry_url": diagnostics.get("registry_url"),
                    "diagnostics": diagnostics.get("diagnostics", []),
                }
            )
        except Exception:
            error_log.error("webui_extensions_routes.get_extensions_registry", exc_info=True)
            return _extension_error("Extensions registry is unavailable.", "extensions_registry_unavailable", 500)

    @bp.route("/extensions/installed", methods=["GET"])
    def get_installed_extensions() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"available": False, "extensions": []}), 200
            return jsonify({"available": True, "extensions": svc.installed_extensions()})
        except Exception:
            error_log.error("webui_extensions_routes.get_installed_extensions", exc_info=True)
            return _extension_error("Installed extensions are unavailable.", "extensions_installed_unavailable", 500)

    @bp.route("/extensions/providers", methods=["GET"])
    def get_extension_providers() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = _get_extensions_runtime(svc)
            if svc is None:
                return jsonify({"available": False, "providers": []}), 200
            return jsonify(
                {
                    "available": True,
                    "runtime_status": getattr(svc, "runtime_status", "ready" if runtime is not None else "unavailable"),
                    "providers": svc.provider_rows(runtime),
                }
            )
        except Exception:
            error_log.error("webui_extensions_routes.get_extension_providers", exc_info=True)
            return _extension_error("Extension providers are unavailable.", "extensions_providers_unavailable", 500)

    @bp.route("/providers/catalog", methods=["GET"])
    def get_provider_catalog() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = _get_extensions_runtime(svc)
            if svc is None:
                return jsonify({"available": False, "providers": [], "models": []}), 200
            capability = (request.args.get("capability") or "").strip() or None
            payload = svc.provider_catalog(runtime=runtime, capability=capability)
            payload["available"] = True
            payload["capability"] = capability
            payload["runtime_status"] = getattr(svc, "runtime_status", "ready" if runtime is not None else "unavailable")
            return jsonify(payload)
        except Exception:
            error_log.error("webui_extensions_routes.get_provider_catalog", exc_info=True)
            return _extension_error("Provider catalog is unavailable.", "extensions_provider_catalog_unavailable", 500)

    @bp.route("/extensions/tabs", methods=["GET"])
    def get_extension_tabs() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = _get_extensions_runtime(svc)
            if svc is None:
                return jsonify({"available": False, "tabs": []}), 200
            return jsonify(
                {
                    "available": True,
                    "runtime_status": getattr(svc, "runtime_status", "ready" if runtime is not None else "unavailable"),
                    "tabs": svc.extension_tabs(runtime=runtime),
                }
            )
        except Exception:
            error_log.error("webui_extensions_routes.get_extension_tabs", exc_info=True)
            return _extension_error("Extension tabs are unavailable.", "extensions_tabs_unavailable", 500)

    @bp.route("/extensions/<extension_id>/tab", methods=["GET"])
    def get_extension_tab(extension_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            runtime = _get_extensions_runtime(svc)
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            if runtime is None:
                return jsonify({"error": "Extension runtime is still loading"}), 503
            payload = svc.extension_tab_payload(extension_id, runtime=runtime)
            payload["available"] = True
            return jsonify(payload)
        except ValueError:
            # Extension not found or not loaded — 404, not 400.
            error_log.error("webui_extensions_routes.get_extension_tab", exc_info=True)
            return _extension_error("Extension not found or not loaded.", "extension_tab_not_found", 404)
        except Exception:
            error_log.error("webui_extensions_routes.get_extension_tab", exc_info=True)
            return _extension_error("Extension tab payload is unavailable.", "extension_tab_unavailable", 500)

    @bp.route("/extensions/ui", methods=["GET"])
    def get_extension_ui_payload() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"available": False, "extensions": [], "failed": []}), 200
            payload = svc.ui_payload()
            payload["available"] = True
            return jsonify(payload)
        except Exception:
            error_log.error("webui_extensions_routes.get_extension_ui_payload", exc_info=True)
            return _extension_error("Extension UI payload is unavailable.", "extensions_ui_unavailable", 500)

    @bp.route("/extensions/<extension_id>/details", methods=["GET"])
    def get_extension_details(extension_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            return jsonify(svc.extension_details(extension_id, ref=request.args.get("ref")))
        except ValueError:
            error_log.error("webui_extensions_routes.get_extension_details", exc_info=True)
            return _extension_error("Extension details request was rejected.", "extension_details_rejected", 400)
        except Exception:
            error_log.error("webui_extensions_routes.get_extension_details", exc_info=True)
            return _extension_error("Extension details are unavailable.", "extension_details_unavailable", 502)

    @bp.route("/extensions/<extension_id>/actions/<action_id>", methods=["POST"])
    def run_extension_action(extension_id: str, action_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            runtime = _get_extensions_runtime(svc)
            if svc is None or runtime is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.run_extension_action(
                extension_id,
                action_id,
                payload=body,
                runtime=runtime,
            )
            return jsonify(result)
        except Exception:
            error_log.error("webui_extensions_routes.run_extension_action", exc_info=True)
            return _extension_error("Extension action failed.", "extension_action_failed", 400)

    @bp.route("/extensions/<extension_id>/sandbox/restart", methods=["POST"])
    def restart_extension_sandbox(extension_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            return jsonify(svc.restart_extension_sandbox(extension_id))
        except Exception:
            error_log.error("webui_extensions_routes.restart_extension_sandbox", exc_info=True)
            return _extension_error("Extension sandbox restart failed.", "extension_sandbox_restart_failed", 400)

    @bp.route("/extensions/<extension_id>/sandbox/kill", methods=["POST"])
    def kill_extension_sandbox(extension_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            return jsonify(svc.kill_extension_sandbox(extension_id))
        except Exception:
            error_log.error("webui_extensions_routes.kill_extension_sandbox", exc_info=True)
            return _extension_error("Extension sandbox kill failed.", "extension_sandbox_kill_failed", 400)

    @bp.route("/extensions/<extension_id>/assets/<path:asset_path>", methods=["GET"])
    def get_extension_asset(extension_id: str, asset_path: str) -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 404
            path = svc.resolve_asset_path(extension_id, asset_path)
            return send_file(path)
        except Exception:
            return jsonify({"error": "extension asset not found"}), 404

    @bp.route("/extensions/install", methods=["POST"])
    def install_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.install(
                str(body.get("extension_id") or ""),
                version=body.get("version"),
                target={
                    **(body.get("target") if isinstance(body.get("target"), dict) else {}),
                    **(
                        {"allow_capability_expansion": body.get("allow_capability_expansion")}
                        if "allow_capability_expansion" in body
                        else {}
                    ),
                    **(
                        {"accepted_capabilities": body.get("accepted_capabilities")}
                        if "accepted_capabilities" in body
                        else {}
                    ),
                },
            )
            return jsonify(result), 202
        except Exception:
            error_log.error("webui_extensions_routes.install_extension", exc_info=True)
            return _extension_error("Extension install request was rejected.", "extension_install_rejected", 400)

    @bp.route("/extensions/remove", methods=["POST"])
    def remove_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.remove(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception:
            error_log.error("webui_extensions_routes.remove_extension", exc_info=True)
            return _extension_error("Extension remove request was rejected.", "extension_remove_rejected", 400)

    @bp.route("/extensions/enable", methods=["POST"])
    def enable_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.enable(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception:
            error_log.error("webui_extensions_routes.enable_extension", exc_info=True)
            return _extension_error("Extension enable request was rejected.", "extension_enable_rejected", 400)

    @bp.route("/extensions/disable", methods=["POST"])
    def disable_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.disable(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception:
            error_log.error("webui_extensions_routes.disable_extension", exc_info=True)
            return _extension_error("Extension disable request was rejected.", "extension_disable_rejected", 400)
