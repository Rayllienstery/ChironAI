"""Custom upstream provider routes for the WebUI blueprint."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request

from application.custom_openai_providers import (
    delete_custom_openai_provider,
    get_custom_openai_provider_record,
    list_custom_openai_providers_public,
    upsert_custom_openai_provider,
    validate_provider_id,
)
from application.openai_compatible_provider import OpenAICompatibleProvider
from application.host_provider_sync import sync_custom_openai_providers
from api.http.extensions_service_access import get_extensions_runtime, get_extensions_service


def register_providers_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    settings_repository_factory: Callable[[], Any],
) -> None:
    def _settings_repo() -> Any:
        return settings_repository_factory()

    def _sync_runtime() -> None:
        svc = get_extensions_service(current_app)
        runtime = get_extensions_runtime(current_app, svc)
        if runtime is None:
            return
        sync_custom_openai_providers(runtime.registry, _settings_repo())
        if svc is not None and hasattr(svc, "invalidate_provider_rows_cache"):
            svc.invalidate_provider_rows_cache()

    @bp.route("/providers/custom", methods=["GET"])
    def list_custom_providers() -> Any:
        try:
            return jsonify({"providers": list_custom_openai_providers_public(_settings_repo())})
        except Exception as exc:
            error_log.error("webui_providers_routes.list_custom_providers", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/providers/custom", methods=["POST"])
    def create_custom_provider() -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            provider = upsert_custom_openai_provider(
                _settings_repo(),
                provider_id=str(body.get("id") or ""),
                display_name=str(body.get("display_name") or body.get("id") or ""),
                base_url=str(body.get("base_url") or ""),
                api_key=str(body.get("api_key") or ""),
                default_headers=body.get("default_headers") if isinstance(body.get("default_headers"), dict) else {},
                organization=str(body.get("organization") or ""),
                manual_models=body.get("manual_models") if isinstance(body.get("manual_models"), list) else [],
                enabled=bool(body.get("enabled", True)),
            )
            _sync_runtime()
            return jsonify(provider), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            error_log.error("webui_providers_routes.create_custom_provider", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/providers/custom/<provider_id>", methods=["PUT"])
    def update_custom_provider(provider_id: str) -> Any:
        try:
            validate_provider_id(provider_id)
            body = request.get_json(force=True, silent=True) or {}
            provider = upsert_custom_openai_provider(
                _settings_repo(),
                provider_id=provider_id,
                display_name=str(body.get("display_name") or provider_id),
                base_url=str(body.get("base_url") or ""),
                api_key=str(body.get("api_key") or "").strip() or None,
                default_headers=body.get("default_headers") if isinstance(body.get("default_headers"), dict) else {},
                organization=str(body.get("organization") or ""),
                manual_models=body.get("manual_models") if isinstance(body.get("manual_models"), list) else [],
                enabled=bool(body.get("enabled", True)),
            )
            _sync_runtime()
            return jsonify(provider)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            error_log.error("webui_providers_routes.update_custom_provider", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/providers/custom/<provider_id>", methods=["DELETE"])
    def delete_custom_provider_route(provider_id: str) -> Any:
        try:
            validate_provider_id(provider_id)
            deleted = delete_custom_openai_provider(_settings_repo(), provider_id)
            if not deleted:
                return jsonify({"error": "Provider not found"}), 404
            _sync_runtime()
            return jsonify({"ok": True})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            error_log.error("webui_providers_routes.delete_custom_provider_route", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/providers/custom/<provider_id>/test", methods=["POST"])
    def test_custom_provider(provider_id: str) -> Any:
        try:
            validate_provider_id(provider_id)
            record = get_custom_openai_provider_record(_settings_repo(), provider_id)
            if record is None:
                return jsonify({"error": "Provider not found"}), 404
            result = OpenAICompatibleProvider(record).test_connection()
            status = 200 if result.get("ok") else 502
            return jsonify(result), status
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            error_log.error("webui_providers_routes.test_custom_provider", exc_info=True)
            return jsonify({"ok": False, "status": "error", "message": str(exc)}), 502


__all__ = ["register_providers_routes"]
