"""Push crawl results to md_ingestion_service via HTTP (core/contracts/md_ingestion_api)."""

from __future__ import annotations

import os
from typing import Any

import requests

from crawler_service.domain.entities import CrawlResult
from crawler_service.domain.ports import MdIngestionClient

MD_INGESTION_URL = os.getenv("MD_INGESTION_SERVICE_URL", "http://localhost:5002")


class MdIngestionHttpAdapter:
    """MdIngestionClient that POSTs to md_ingestion_service."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or MD_INGESTION_URL).rstrip("/")

    def push_crawl_results(
        self,
        source_id: str,
        results: list[CrawlResult],
        collection: str,
    ) -> dict[str, Any]:
        # Contract: POST /ingest/from-crawl with body { source_id, documents: [ { url, html, ... } ], collection }
        url = f"{self._base_url}/ingest/from-crawl"
        documents = [{"url": r.url, "html": r.html, "source_id": r.source_id} for r in results]
        try:
            resp = requests.post(
                url,
                json={"source_id": source_id, "documents": documents, "collection": collection},
                timeout=600,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            return {"accepted": 0, "errors": [str(e)]}


__all__ = ["MdIngestionHttpAdapter"]
