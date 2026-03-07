"""
RAG domain errors.

Business-level failures (retrieval, embedding, rerank) without
infrastructure-specific details.
"""


class RetrievalError(Exception):
    """Raised when RAG retrieval fails in a domain-visible way."""


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class RerankError(Exception):
    """Raised when reranking cannot be completed."""


__all__ = ["RetrievalError", "EmbeddingError", "RerankError"]
