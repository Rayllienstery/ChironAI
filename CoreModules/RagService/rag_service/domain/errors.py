"""
RAG domain errors — re-exported from the canonical ``error_manager`` package.

All exception classes are defined once in ``CoreModules/ErrorManager/error_manager/exceptions.py``.
This module keeps its original import path (``rag_service.domain.errors``) working for all
existing callers.
"""

from core.contracts.errors import (  # noqa: F401
    EmbeddingError,
    RerankError,
    RetrievalError,
)

__all__ = ["RetrievalError", "EmbeddingError", "RerankError"]
