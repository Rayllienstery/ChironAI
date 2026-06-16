"""
Shared Qdrant point construction for RAG indexers (dense + optional sparse).

Single place for vector payload shape so crawler, sinks, and search stay aligned.
"""

from __future__ import annotations

from typing import Any

from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def dense_vectors_config(vector_size: int) -> dict[str, Any]:
    """Qdrant ``vectors_config`` for dense-only collections (named ``dense`` vector)."""
    from qdrant_client.http.models import Distance, VectorParams

    return {
        DENSE_VECTOR_NAME: VectorParams(size=vector_size, distance=Distance.COSINE),
    }


def hybrid_vectors_config(vector_size: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(vectors_config, sparse_vectors_config)`` for hybrid collections."""
    from qdrant_client.http.models import SparseVectorParams

    return (
        dense_vectors_config(vector_size),
        {SPARSE_VECTOR_NAME: SparseVectorParams()},
    )


def build_named_vectors(
    chunk_text: str,
    dense_vector: list[float],
    *,
    hybrid_sparse: bool,
) -> dict[str, Any]:
    """Named vector payload for Qdrant upsert (dense-only or dense+sparse)."""
    if not hybrid_sparse:
        return {DENSE_VECTOR_NAME: dense_vector}
    idx, vals = text_to_sparse_vector(normalize_text_for_sparse(chunk_text))
    return {
        DENSE_VECTOR_NAME: dense_vector,
        SPARSE_VECTOR_NAME: {"indices": idx, "values": vals},
    }


__all__ = [
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "build_named_vectors",
    "dense_vectors_config",
    "hybrid_vectors_config",
    "normalize_text_for_sparse",
    "text_to_sparse_vector",
]
