"""
Domain-level error types — re-exported from the canonical ``error_manager`` package.

All exception classes are defined once in ``CoreModules/ErrorManager/error_manager/exceptions.py``.
This module keeps its original import path (``domain.errors``) working for all existing callers.
"""

from error_manager.exceptions import (  # noqa: F401
    ChironError,
    CrawlError,
    EmbeddingError,
    IndexingError,
    IngestionError,
    PipelineError,
    RerankError,
    RetrievalError,
)

__all__ = [
    "ChironError",
    "RetrievalError",
    "EmbeddingError",
    "RerankError",
    "IndexingError",
    "CrawlError",
    "IngestionError",
    "PipelineError",
]
