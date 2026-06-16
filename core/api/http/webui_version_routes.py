"""Version and changelog routes for the WebUI blueprint."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify

from core.changelog_helper import get_latest_changelog_content
from core.version import APP_NAME, APP_STAGE, VERSION
from webui_backend.paths import project_root


def register_version_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/version", methods=["GET"])
    def get_version() -> Any:
        """Return current app version and latest changelog."""
        try:
            root = project_root()
            changelog = get_latest_changelog_content(root)
            return jsonify({
                "version": VERSION,
                "app_name": APP_NAME,
                "stage": APP_STAGE,
                "changelog": changelog,
                "display_name": f"{APP_NAME} {APP_STAGE} {VERSION}"
            })
        except Exception as e:
            error_log.error("webui_version_routes.get_version", exc_info=True)
            return jsonify({
                "version": VERSION,
                "app_name": APP_NAME,
                "stage": APP_STAGE,
                "display_name": f"{APP_NAME} {APP_STAGE} {VERSION}",
                "error": str(e)
            })


__all__ = ["register_version_routes"]
