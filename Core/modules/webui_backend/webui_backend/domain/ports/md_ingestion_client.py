"""Port: call md_ingestion_service via HTTP (core/contracts/md_ingestion_api)."""

from __future__ import annotations

from typing import Any, Protocol


class MdIngestionClient(Protocol):
    """Port for md_ingestion service."""

    def ingest_local(self, source_path: str, source_id: str, collection: str) -> dict[str, Any]:
        """POST /ingest/local."""
        ...


__all__ = ["MdIngestionClient"]
