"""Extension-management routes for WebUI."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request


def _get_extensions_service() -> Any:
    return current_app.extensions.get("llm_extensions_service")


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
            return jsonify(
                {
                    "available": True,
                    "registry": svc.registry_entries(),
                    "registry_url": getattr(getattr(svc, "_registry_client", None), "registry_url", None),
                }
            )
        except Exception as e:
            error_log.error("webui_extensions_routes.get_extensions_registry", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/extensions/installed", methods=["GET"])
    def get_installed_extensions() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"available": False, "extensions": []}), 200
            return jsonify({"available": True, "extensions": svc.installed_extensions()})
        except Exception as e:
            error_log.error("webui_extensions_routes.get_installed_extensions", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/extensions/providers", methods=["GET"])
    def get_extension_providers() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = current_app.extensions.get("llm_interactor_runtime")
            if svc is None or runtime is None:
                return jsonify({"available": False, "providers": []}), 200
            return jsonify({"available": True, "providers": svc.provider_rows(runtime)})
        except Exception as e:
            error_log.error("webui_extensions_routes.get_extension_providers", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/providers/catalog", methods=["GET"])
    def get_provider_catalog() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = current_app.extensions.get("llm_interactor_runtime")
            if svc is None or runtime is None:
                return jsonify({"available": False, "providers": [], "models": []}), 200
            capability = (request.args.get("capability") or "").strip() or None
            payload = svc.provider_catalog(runtime=runtime, capability=capability)
            payload["available"] = True
            payload["capability"] = capability
            return jsonify(payload)
        except Exception as e:
            error_log.error("webui_extensions_routes.get_provider_catalog", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/extensions/tabs", methods=["GET"])
    def get_extension_tabs() -> Any:
        try:
            svc = _get_extensions_service()
            runtime = current_app.extensions.get("llm_interactor_runtime")
            if svc is None or runtime is None:
                return jsonify({"available": False, "tabs": []}), 200
            return jsonify({"available": True, "tabs": svc.extension_tabs(runtime=runtime)})
        except Exception as e:
            error_log.error("webui_extensions_routes.get_extension_tabs", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/extensions/<extension_id>/tab", methods=["GET"])
    def get_extension_tab(extension_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            runtime = current_app.extensions.get("llm_interactor_runtime")
            if svc is None or runtime is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            payload = svc.extension_tab_payload(extension_id, runtime=runtime)
            payload["available"] = True
            return jsonify(payload)
        except Exception as e:
            error_log.error("webui_extensions_routes.get_extension_tab", exc_info=True)
            return jsonify({"error": str(e)}), 400

    @bp.route("/extensions/ui", methods=["GET"])
    def get_extension_ui_payload() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"available": False, "extensions": [], "failed": []}), 200
            payload = svc.ui_payload()
            payload["available"] = True
            return jsonify(payload)
        except Exception as e:
            error_log.error("webui_extensions_routes.get_extension_ui_payload", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/extensions/<extension_id>/actions/<action_id>", methods=["POST"])
    def run_extension_action(extension_id: str, action_id: str) -> Any:
        try:
            svc = _get_extensions_service()
            runtime = current_app.extensions.get("llm_interactor_runtime")
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
        except Exception as e:
            error_log.error("webui_extensions_routes.run_extension_action", exc_info=True)
            return jsonify({"error": str(e)}), 400

    @bp.route("/extensions/install", methods=["POST"])
    def install_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.install(str(body.get("extension_id") or ""), version=body.get("version"))
            return jsonify(result), 202
        except Exception as e:
            error_log.error("webui_extensions_routes.install_extension", exc_info=True)
            return jsonify({"error": str(e)}), 400

    @bp.route("/extensions/remove", methods=["POST"])
    def remove_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.remove(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception as e:
            error_log.error("webui_extensions_routes.remove_extension", exc_info=True)
            return jsonify({"error": str(e)}), 400

    @bp.route("/extensions/enable", methods=["POST"])
    def enable_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.enable(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception as e:
            error_log.error("webui_extensions_routes.enable_extension", exc_info=True)
            return jsonify({"error": str(e)}), 400

    @bp.route("/extensions/disable", methods=["POST"])
    def disable_extension() -> Any:
        try:
            svc = _get_extensions_service()
            if svc is None:
                return jsonify({"error": "Extensions runtime is unavailable"}), 503
            body = request.get_json(force=True, silent=True) or {}
            result = svc.disable(str(body.get("extension_id") or ""))
            return jsonify(result), 202
        except Exception as e:
            error_log.error("webui_extensions_routes.disable_extension", exc_info=True)
            return jsonify({"error": str(e)}), 400
