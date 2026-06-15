"""Settings and RAG settings routes for the WebUI blueprint."""

from __future__ import annotations

from typing import Any, Callable

from error_manager.http import error_response as _error_response
from flask import Blueprint, jsonify, request

from config import (
    SERVER_PORT_APP_SETTING,
    SERVER_PORT_LAST_ACTIVE_APP_SETTING,
    _valid_server_port,
    get_server_port_metadata,
)
from infrastructure.database import get_settings_repository

_SERVER_PORT_METADATA_KEYS = {
    "status",
    "server_port_active",
    "server_port_source",
    "server_port_restart_required",
    SERVER_PORT_LAST_ACTIVE_APP_SETTING,
}


def register_settings_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    keyword_collections_repository_factory: Callable[[], Any] | None,
    get_effective_rag_trigger_threshold: Callable[[], int],
    trigger_help_rows: list[dict[str, Any]],
) -> None:
    get_keyword_collections_repository = keyword_collections_repository_factory
    RAG_TRIGGER_HELP_ROWS = trigger_help_rows
    @bp.route("/settings", methods=["GET"])
    def get_settings() -> Any:
        """Get app settings."""
        try:
            settings_repo = get_settings_repository()
            settings = settings_repo.get_all_app_settings()
            # Ensure rag_collection field exists
            if "rag_collection" not in settings:
                settings["rag_collection"] = ""
            settings.update(get_server_port_metadata(settings_repo))
            return jsonify(settings)
        except Exception as e:
            error_log.error("webui_settings_routes.get_settings", exc_info=True)
            return _error_response(e)


    @bp.route("/settings", methods=["POST"])
    def update_settings() -> Any:
        """Update app settings."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            settings_repo = get_settings_repository()

            if SERVER_PORT_APP_SETTING in body:
                port = _valid_server_port(body.get(SERVER_PORT_APP_SETTING))
                if port is None:
                    return _error_response("server_port must be an integer between 1 and 65535", 400)

            for key, value in body.items():
                if key in _SERVER_PORT_METADATA_KEYS:
                    continue
                if key == SERVER_PORT_APP_SETTING and body.get("server_port_source") == "env":
                    continue
                if key == SERVER_PORT_APP_SETTING:
                    value = _valid_server_port(value)
                settings_repo.set_app_setting(key, str(value))

            return jsonify({"status": "ok", **get_server_port_metadata(settings_repo)})
        except Exception as e:
            error_log.error("webui_settings_routes.update_settings", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-keyword-collections", methods=["GET"])
    def get_rag_keyword_collections() -> Any:
        """Return all RAG trigger keyword collections (from rag_service module)."""
        if get_keyword_collections_repository is None:
            return jsonify({"collections": []})
        try:
            repo = get_keyword_collections_repository()
            collections = repo.get_all()
            return jsonify({"collections": collections})
        except Exception as e:
            error_log.error("webui_settings_routes.get_rag_keyword_collections", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-keyword-collections", methods=["POST"])
    def update_rag_keyword_collections() -> Any:
        """Create or update a collection, or replace all. Body: single {id?, name, enabled, keywords} or {collections: [...]}."""
        if get_keyword_collections_repository is None:
            return _error_response("Keyword collections not available", 503)
        try:
            body = request.get_json(force=True, silent=True) or {}
            repo = get_keyword_collections_repository()
            if "collections" in body:
                # Replace all: upsert each (use None for id when creating new), then delete IDs no longer in list
                new_list = body["collections"]
                existing_ids = {c["id"] for c in repo.get_all()}
                new_ids = set()
                for c in new_list:
                    cid = c.get("id")
                    if cid is None or (isinstance(cid, str) and cid.startswith("new-")):
                        cid = None
                    elif cid not in existing_ids:
                        cid = None
                    saved_id = repo.save_collection(
                        cid,
                        c.get("name", ""),
                        bool(c.get("enabled", True)),
                        c.get("keywords", []),
                    )
                    new_ids.add(saved_id)
                for cid in existing_ids - new_ids:
                    repo.delete_collection(cid)
                return jsonify({"status": "ok", "collections": repo.get_all()})
            # Single collection create/update
            cid = repo.save_collection(
                body.get("id"),
                body.get("name", ""),
                bool(body.get("enabled", True)),
                body.get("keywords", []),
            )
            return jsonify({"status": "ok", "id": cid, "collections": repo.get_all()})
        except Exception as e:
            error_log.error("webui_settings_routes.update_rag_keyword_collections", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-keyword-collections/<collection_id>", methods=["DELETE"])
    def delete_rag_keyword_collection(collection_id: str) -> Any:
        """Delete a RAG keyword collection."""
        if get_keyword_collections_repository is None:
            return _error_response("Keyword collections not available", 503)
        try:
            repo = get_keyword_collections_repository()
            repo.delete_collection(collection_id)
            return jsonify({"status": "ok"})
        except Exception as e:
            error_log.error("webui_settings_routes.delete_rag_keyword_collection", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-trigger-settings", methods=["GET"])
    def get_rag_trigger_settings() -> Any:
        """Return RAG trigger threshold (effective from settings or config) and help table for scoring."""
        try:
            threshold = get_effective_rag_trigger_threshold()
            return jsonify({
                "rag_trigger_threshold": threshold,
                "trigger_help_table": RAG_TRIGGER_HELP_ROWS,
            })
        except Exception as e:
            error_log.error("webui_settings_routes.get_rag_trigger_settings", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-trigger-settings", methods=["POST"])
    def update_rag_trigger_settings() -> Any:
        """Update RAG trigger threshold (persisted to app_settings)."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            raw = body.get("rag_trigger_threshold")
            if raw is None:
                return _error_response("rag_trigger_threshold required", 400)
            val = int(raw)
            if val < 0 or val > 20:
                return _error_response("rag_trigger_threshold must be between 0 and 20", 400)
            settings_repo = get_settings_repository()
            settings_repo.set_app_setting("rag_trigger_threshold", str(val))
            return jsonify({"status": "ok", "rag_trigger_threshold": val})
        except ValueError:
            return _error_response("rag_trigger_threshold must be an integer", 400)
        except Exception as e:
            error_log.error("webui_settings_routes.update_rag_trigger_settings", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-framework-settings", methods=["GET"])
    def get_rag_framework_settings() -> Any:
        """
        Return framework docs RAG settings such as latest TTL days.
        """
        try:
            settings_repo = get_settings_repository()
            raw_ttl = settings_repo.get_app_setting("framework_latest_ttl_days")
            ttl_days = int(raw_ttl) if raw_ttl is not None else 90
            if ttl_days <= 0:
                ttl_days = 90
            return jsonify(
                {
                    "framework_latest_ttl_days": ttl_days,
                }
            )
        except Exception as e:
            error_log.error("webui_settings_routes.get_rag_framework_settings", exc_info=True)
            return _error_response(e)


    @bp.route("/rag-framework-settings", methods=["POST"])
    def update_rag_framework_settings() -> Any:
        """
        Update framework docs RAG settings (e.g. latest TTL days).
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            raw_ttl = body.get("framework_latest_ttl_days")
            if raw_ttl is None:
                return _error_response("framework_latest_ttl_days required", 400)
            ttl_days = int(raw_ttl)
            if ttl_days <= 0 or ttl_days > 3650:
                return _error_response("framework_latest_ttl_days must be between 1 and 3650", 400)
            settings_repo = get_settings_repository()
            settings_repo.set_app_setting("framework_latest_ttl_days", str(ttl_days))
            return jsonify({"status": "ok", "framework_latest_ttl_days": ttl_days})
        except ValueError:
            return _error_response("framework_latest_ttl_days must be an integer", 400)
        except Exception as e:
            error_log.error("webui_settings_routes.update_rag_framework_settings", exc_info=True)
            return _error_response(e)




__all__ = ["register_settings_routes"]
