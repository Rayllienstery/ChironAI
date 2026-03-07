"""
Flask app for WebUI backend.

Serves dashboard/settings/logs and proxies to rag/crawler/md_ingestion via HTTP.
Full route set can be migrated from root api/http/webui_routes.py.
"""

from __future__ import annotations

from flask import Flask, jsonify

from webui_backend.application.use_cases import get_dashboard_stats
from webui_backend.infrastructure.http_crawler_client import HttpCrawlerClient
from webui_backend.infrastructure.http_rag_client import HttpRagClient


def create_app() -> Flask:
    app = Flask(__name__)
    rag_client = HttpRagClient()
    crawler_client = HttpCrawlerClient()

    @app.route("/api/webui/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/webui/dashboard")
    def dashboard():
        stats = get_dashboard_stats(rag_client, crawler_client)
        return jsonify({
            "rag_status": stats.rag_status,
            "crawler_status": stats.crawler_status,
        })

    return app


__all__ = ["create_app"]
