"""
RAG sink via HTTP: send chunks to rag_service (e.g. POST /v1/ingest/chunks).

Contract: core/contracts/rag_api. When rag_service exposes an ingest endpoint,
this client calls it. Until then, this implementation can use a direct Qdrant client
or fail with a clear message.
"""

from __future__ import annotations

import os
from typing import Any

from md_ingestion_service.domain.ports import OutputSink

# Optional: use env RAG_SERVICE_URL for base URL of rag_service
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:5001")


class RagSinkHttp:
    """OutputSink that sends chunks to rag_service over HTTP."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or RAG_SERVICE_URL).rstrip("/")

    def write_chunks(
        self,
        collection: str,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]] | None = None,
    ) -> int:
        """
        POST chunks to rag_service ingest endpoint. If vectors is None, the service
        must compute embeddings (or endpoint may not exist yet — see core/contracts/rag_api).
        """
        # Contract: POST /v1/ingest/chunks with body { "collection": str, "chunks": [...], "vectors": optional }
        # If endpoint is not implemented, raise with a clear message.
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests required for RagSinkHttp") from None
        url = f"{self._base_url}/v1/ingest/chunks"
        payload = {"collection": collection, "chunks": chunks}
        if vectors is not None:
            payload["vectors"] = vectors
        try:
            resp = requests.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()
            return int(data.get("points_written", len(chunks)))
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"RAG service not reachable at {self._base_url}. Start rag_service or set RAG_SERVICE_URL."
            ) from e
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise RuntimeError(
                    "RAG service does not expose /v1/ingest/chunks yet. Use direct Qdrant or add the endpoint to rag_service."
                ) from e
            raise RuntimeError(f"RAG ingest failed: {e}") from e


__all__ = ["RagSinkHttp"]
