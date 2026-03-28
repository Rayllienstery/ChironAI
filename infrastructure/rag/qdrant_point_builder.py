"""
Shared Qdrant point construction for RAG indexers (dense + optional sparse).

Single place for vector payload shape so crawler and external sinks stay aligned.
"""

from __future__ import annotations

from typing import Any

from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def build_named_vectors(
    chunk_text: str,
    dense_vector: list[float],
    *,
    hybrid_sparse: bool,
) -> Any:
    """
    Return either a plain dense list (legacy single-vector collection) or a dict
    of named vectors for hybrid collections.
    """
    if not hybrid_sparse:
        return dense_vector
    idx, vals = text_to_sparse_vector(normalize_text_for_sparse(chunk_text))
    return {
        DENSE_VECTOR_NAME: dense_vector,
        SPARSE_VECTOR_NAME: {"indices": idx, "values": vals},
    }


__all__ = [
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "build_named_vectors",
    "normalize_text_for_sparse",
    "text_to_sparse_vector",
]
