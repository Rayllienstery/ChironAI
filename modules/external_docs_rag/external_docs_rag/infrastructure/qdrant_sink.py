"""
Qdrant chunk sink: ensure collection exists, upsert points with vectors.
Uses qdrant_client when available; otherwise no-op or raise.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, PointStruct, VectorParams
    _HAS_QDRANT = True
except ImportError:
    QdrantClient = None  # type: ignore
    PointStruct = None  # type: ignore
    VectorParams = None  # type: ignore
    Distance = None  # type: ignore
    _HAS_QDRANT = False


def _point_id_from_hash(chunk_hash: str) -> int:
    """Deterministic numeric id from content hash (first 8 bytes as signed int)."""
    h = hashlib.sha256(chunk_hash.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False) % (2**63)


class QdrantChunkSink:
    """Write chunks and vectors to a Qdrant collection. Creates collection if missing."""

    def __init__(self, base_url: str = "http://localhost:6333") -> None:
        self._base_url = base_url.rstrip("/")
        self._client: QdrantClient | None = None

    def _get_client(self) -> QdrantClient:
        if not _HAS_QDRANT or QdrantClient is None:
            raise RuntimeError("qdrant-client is required for QdrantChunkSink. pip install qdrant-client")
        if self._client is None:
            self._client = QdrantClient(url=self._base_url)
        return self._client

    def _ensure_collection(self, collection_name: str, vector_size: int) -> None:
        client = self._get_client()
        try:
            info = client.get_collection(collection_name)
            # Check vector size matches
            if hasattr(info, "config") and info.config and hasattr(info.config, "params"):
                size = getattr(info.config.params, "size", None)
                if size is not None and size != vector_size:
                    client.recreate_collection(
                        collection_name,
                        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                    )
        except Exception:
            client.recreate_collection(
                collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def write_chunks(
        self,
        collection_name: str,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
        vector_size: int,
    ) -> int:
        """
        Ensure collection exists, then upsert points. Chunks must have at least "text";
        optional source_id, path, url, section_path for payload.
        Returns number of points written.
        """
        if not chunks or not vectors or len(chunks) != len(vectors):
            return 0
        if not _HAS_QDRANT or PointStruct is None:
            return 0
        self._ensure_collection(collection_name, vector_size)
        client = self._get_client()
        points: list[PointStruct] = []
        for i, (payload, vec) in enumerate(zip(chunks, vectors)):
            text = payload.get("text", "")
            source_id = payload.get("source_id", "external")
            path = payload.get("path", "")
            section_path = payload.get("section_path") or []
            chunk_hash = f"{source_id}:{path}:{':'.join(section_path)}:{text}"
            point_id = _point_id_from_hash(chunk_hash)
            full_payload = {
                "text": text,
                "source": source_id,
                "path": path,
                "url": payload.get("url", ""),
                "section_path": section_path,
            }
            points.append(PointStruct(id=point_id, vector=vec, payload=full_payload))
        client.upsert(collection_name=collection_name, points=points)
        return len(points)


__all__ = ["QdrantChunkSink"]
