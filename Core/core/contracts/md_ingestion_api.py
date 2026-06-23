"""
MD Ingestion service API contract.

Clients (crawler_service, webui_backend, WebUI scripts) trigger or query ingestion.
Output to the vector store is typically followed by RAG retrieval via the main stack.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class IngestLocalRequest(TypedDict, total=False):
    """POST /ingest/local (planned standalone service body shape)."""

    source_path: str
    source_id: str
    collection: str | None


class IngestJobStartedResponse(TypedDict):
    job_id: str
    status: Literal["started"]


class IngestStatusResponse(TypedDict, total=False):
    """GET /ingest/status/{job_id}."""

    status: Literal["running", "done", "failed"]
    files_processed: int
    chunks_indexed: int
    error: str | None


__all__ = [
    "IngestLocalRequest",
    "IngestJobStartedResponse",
    "IngestStatusResponse",
]
