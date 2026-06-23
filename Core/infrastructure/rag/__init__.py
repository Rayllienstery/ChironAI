"""RAG indexing helpers (sparse vectors, Qdrant point shapes)."""

from infrastructure.rag.qdrant_point_builder import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    build_named_vectors,
    dense_vectors_config,
    hybrid_vectors_config,
)
from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector

__all__ = [
    "DENSE_VECTOR_NAME",
    "SPARSE_VECTOR_NAME",
    "build_named_vectors",
    "dense_vectors_config",
    "hybrid_vectors_config",
    "normalize_text_for_sparse",
    "text_to_sparse_vector",
]
