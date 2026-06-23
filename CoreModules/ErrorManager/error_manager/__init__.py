"""
error_manager — canonical error types and HTTP helpers for ChironAI.

Public API::

    from error_manager import ChironError, RetrievalError, error_response
    from error_manager.exceptions import EmbeddingError, PipelineError
    from error_manager.http import error_response
    from error_manager.codes import RETRIEVAL_ERROR
"""

from error_manager.exceptions import (
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
from error_manager.http import error_response

__all__ = [
    # Base
    "ChironError",
    # Domain
    "RetrievalError",
    "EmbeddingError",
    "RerankError",
    "PipelineError",
    "IndexingError",
    "IngestionError",
    "CrawlError",
    # Auth / proxy
    "AuthError",
    "ProxyError",
    # Request
    "ValidationError",
    "NotFoundError",
    # HTTP helper
    "error_response",
]
