"""
Domain-level error types.

These exceptions represent business-level failures (retrieval, embedding,
indexing, crawling) without leaking infrastructure-specific details.
Infrastructure adapters should catch low-level exceptions and rethrow
them as these domain errors.
"""

class RetrievalError(Exception):
    """Raised when RAG retrieval fails in a domain-visible way."""


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class RerankError(Exception):
    """Raised when reranking cannot be completed."""


class IndexingError(Exception):
    """Raised when indexing content into the vector store fails."""


class CrawlError(Exception):
    """Raised when crawling sources fails."""

