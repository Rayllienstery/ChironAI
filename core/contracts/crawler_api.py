"""
Crawler service API contract.

Endpoints for starting/stopping crawls and querying status.
Clients (webui_backend) use this to trigger crawls and get status.
"""

from __future__ import annotations

# POST /crawl/start — body: { "source_id": str } or { "source_ids": list[str] }
# Response: { "job_id": str, "status": "started" }
# GET /crawl/status/{job_id} — response: { "status": "running" | "done" | "failed", "sources_crawled": int, "pages": int, "error": str | null }
# GET /crawl/sources — response: { "sources": [ { "id", "url", "max_depth", "crawler" }, ... ] }

__all__ = []
