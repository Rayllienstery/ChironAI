"""
Qdrant chunk sink: ensure collection exists, upsert points with vectors.
Uses qdrant_client when available; otherwise no-op or raise.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PointStruct

# qdrant_client is imported lazily inside methods to avoid the ~800ms startup
# cost when the sink is not actually used.  _HAS_QDRANT is populated on first use.
_HAS_QDRANT: bool | None = None


def _ensure_qdrant_available() -> bool:
    """Return True if qdrant_client can be imported; caches the result."""
    global _HAS_QDRANT
    if _HAS_QDRANT is None:
        try:
            import qdrant_client  # noqa: F401
            _HAS_QDRANT = True
        except ImportError:
            _HAS_QDRANT = False
    return _HAS_QDRANT


def _point_id_from_hash(chunk_hash: str) -> int:
    """Deterministic numeric id from content hash (first 8 bytes as signed int)."""
    h = hashlib.sha256(chunk_hash.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False) % (2**63)


def _collection_has_sparse(client: Any, collection_name: str) -> bool:
    try:
        info = client.get_collection(collection_name)
        params = info.config.params
        sv = getattr(params, "sparse_vectors", None)
        if sv is None:
            return False
        if isinstance(sv, dict):
            return len(sv) > 0
        return bool(sv)
    except Exception:
        return False


class QdrantChunkSink:
    """Write chunks and vectors to a Qdrant collection. Creates collection if missing."""

    def __init__(self, base_url: str = "http://localhost:6333") -> None:
        self._base_url = base_url.rstrip("/")
        self._client: QdrantClient | None = None

    def _get_client(self) -> QdrantClient:
        if not _ensure_qdrant_available():
            raise RuntimeError("qdrant-client is required for QdrantChunkSink. pip install qdrant-client")
        if self._client is None:
            from qdrant_client import QdrantClient as _QdrantClient  # noqa: PLC0415
            self._client = _QdrantClient(url=self._base_url)
        return self._client

    def _ensure_collection(self, collection_name: str, vector_size: int, *, hybrid_sparse: bool) -> None:
        from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams  # noqa: PLC0415
        client = self._get_client()
        try:
            info = client.get_collection(collection_name)
            if hasattr(info, "config") and info.config and hasattr(info.config, "params"):
                size = getattr(info.config.params, "size", None)
                if size is not None and size != vector_size:
                    client.recreate_collection(
                        collection_name,
                        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                    )
            return
        except Exception:
            pass
        if hybrid_sparse:
            client.recreate_collection(
                collection_name,
                vectors_config={
                    "dense": VectorParams(size=vector_size, distance=Distance.COSINE),
                },
                sparse_vectors_config={"sparse": SparseVectorParams()},
            )
        else:
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
        if not _ensure_qdrant_available():
            return 0
        hybrid_cfg = False
        try:
            from application.rag.hybrid_sparse import is_hybrid_sparse_enabled

            hybrid_cfg = bool(is_hybrid_sparse_enabled())
        except Exception:
            try:
                from config import get_retrieval_bool

                hybrid_cfg = bool(get_retrieval_bool("hybrid_sparse_enabled", True))
            except Exception:
                hybrid_cfg = False
        self._ensure_collection(collection_name, vector_size, hybrid_sparse=hybrid_cfg)
        client = self._get_client()
        effective_hybrid = hybrid_cfg and _collection_has_sparse(client, collection_name)
        try:
            from infrastructure.rag.qdrant_point_builder import build_named_vectors
        except Exception:

            def build_named_vectors(text: str, dense: list[float], *, hybrid_sparse: bool) -> Any:
                return dense

        from qdrant_client.http.models import PointStruct  # noqa: PLC0415
        points: list[PointStruct] = []
        for payload, vec in zip(chunks, vectors):
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
            vec_payload = build_named_vectors(text, vec, hybrid_sparse=effective_hybrid)
            points.append(PointStruct(id=point_id, vector=vec_payload, payload=full_payload))
        client.upsert(collection_name=collection_name, points=points)
        return len(points)


__all__ = ["QdrantChunkSink"]
