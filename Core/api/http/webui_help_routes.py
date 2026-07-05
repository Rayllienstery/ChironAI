"""In-app help / knowledge base routes for the WebUI blueprint."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from application.webui_help import bundled_help_dir, load_help_article, load_help_index, search_help
from webui_backend.paths import project_root


def register_help_routes(bp: Blueprint, *, error_log: Any) -> None:
    @bp.route("/help/search", methods=["GET"])
    def search_help_articles() -> Any:
        """Search help article titles, tags, and bodies."""
        try:
            query = str(request.args.get("q") or "").strip()
            if not query:
                return jsonify({"results": []})
            help_root = bundled_help_dir(project_root())
            results = search_help(help_root, query)
            return jsonify({"query": query, "results": results})
        except Exception as exc:
            error_log.error("webui_help_routes.search_help_articles", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/help/<slug>", methods=["GET"])
    def get_help_article(slug: str) -> Any:
        """Return one help article by slug."""
        try:
            help_root = bundled_help_dir(project_root())
            article = load_help_article(help_root, slug)
            if article is None:
                return jsonify({"error": "Help article not found"}), 404
            return jsonify(article)
        except Exception as exc:
            error_log.error("webui_help_routes.get_help_article", exc_info=True)
            return jsonify({"error": str(exc)}), 500

    @bp.route("/help", methods=["GET"])
    def list_help_articles() -> Any:
        """List help article index entries."""
        try:
            help_root = bundled_help_dir(project_root())
            articles = load_help_index(help_root)
            return jsonify({"articles": articles})
        except Exception as exc:
            error_log.error("webui_help_routes.list_help_articles", exc_info=True)
            return jsonify({"error": str(exc)}), 500


__all__ = ["register_help_routes"]
