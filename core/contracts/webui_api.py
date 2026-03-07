"""
WebUI backend API contract.

Endpoints consumed by the React frontend. All other services (RAG, crawler, md_ingestion)
are called by webui_backend via their contracts; the frontend talks only to webui_backend.
"""

from __future__ import annotations

# GET /api/webui/... — dashboard, models, prompts, logs, settings, chat (proxy to RAG), etc.
# See existing api/http/webui_routes.py for current shape. Migrate routes into modules/webui_backend.

__all__ = []
