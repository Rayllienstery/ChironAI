"""Compatibility facade for canonical ChironAI exception classes."""

from core.contracts.errors import (
    AuthError,
    ChironError,
    CrawlError,
    EmbeddingError,
    IndexingError,
    IngestionError,
    NotFoundError,
    PipelineError,
    ProxyError,
    RerankError,
    RetrievalError,
    ValidationError,
)

__all__ = [
    "ChironError",
    "RetrievalError",
    "EmbeddingError",
    "RerankError",
    "PipelineError",
    "IndexingError",
    "IngestionError",
    "CrawlError",
    "AuthError",
    "ProxyError",
    "ValidationError",
    "NotFoundError",
]
