"""
MD Ingestion service API contract.

Endpoint and DTO descriptions for clients (crawler_service, webui_backend) that trigger
or query ingestion. Output to RAG is via rag_service contract (e.g. POST /v1/ingest/chunks).
"""

from __future__ import annotations

# POST /ingest/local — body: { "source_path": str, "source_id": str, "collection": str | null }
# Response: { "job_id": str, "status": "started" }
# GET /ingest/status/{job_id} — response: { "status": "running" | "done" | "failed", "files_processed": int, "chunks_indexed": int, "error": str | null }

__all__ = []
