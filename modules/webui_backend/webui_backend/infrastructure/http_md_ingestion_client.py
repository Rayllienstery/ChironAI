"""MdIngestionClient implementation via HTTP to md_ingestion_service."""

from __future__ import annotations

import os
from typing import Any

import requests

from webui_backend.domain.ports import MdIngestionClient

MD_INGESTION_URL = os.getenv("MD_INGESTION_SERVICE_URL", "http://localhost:5002")


class HttpMdIngestionClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or MD_INGESTION_URL).rstrip("/")

    def ingest_local(self, source_path: str, source_id: str, collection: str) -> dict[str, Any]:
        r = requests.post(
            f"{self._base}/ingest/local",
            json={"source_path": source_path, "source_id": source_id, "collection": collection},
            timeout=600,
        )
        r.raise_for_status()
        return r.json()


__all__ = ["HttpMdIngestionClient"]
