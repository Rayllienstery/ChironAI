"""
Canonical ChironAI exception hierarchy.

All domain-level errors across the codebase subclass ChironError so that:
- Every error carries a string ``code`` (machine-readable), a human ``message``, and
  optional ``details`` (list of strings for validation breakdowns, etc.).
- HTTP layers can call ``error.to_dict()`` to produce a consistent response body.
- Individual CoreModules keep their own ``domain/errors.py`` files as thin re-exports
  of these classes so existing import paths remain unchanged.

Usage::

    from error_manager.exceptions import RetrievalError

    raise RetrievalError("Qdrant timed out", cause=original_exc)
"""

from __future__ import annotations

from typing import Any

from error_manager import codes


class ChironError(Exception):
    """Base class for all ChironAI domain errors."""

    code: str = codes.CHIRON_ERROR
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: list[str] | None = None,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.context = context
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the standard ``{"code": ..., "message": ...}`` shape."""
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            d["details"] = self.details
        return d

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# RAG / retrieval pipeline errors
# ---------------------------------------------------------------------------

class RetrievalError(ChironError):
    """Raised when RAG retrieval fails in a domain-visible way."""

    code = codes.RETRIEVAL_ERROR
    http_status = 502


class EmbeddingError(ChironError):
    """Raised when embedding generation fails."""

    code = codes.EMBEDDING_ERROR
    http_status = 502


class RerankError(ChironError):
    """Raised when reranking cannot be completed."""

    code = codes.RERANK_ERROR
    http_status = 502


class PipelineError(ChironError):
    """Raised when a RAG pipeline step fails fatally."""

    code = codes.PIPELINE_ERROR
    http_status = 500


# ---------------------------------------------------------------------------
# Ingestion / crawling errors
# ---------------------------------------------------------------------------

class IndexingError(ChironError):
    """Raised when indexing content into the vector store fails."""

    code = codes.INDEXING_ERROR
    http_status = 500


class IngestionError(ChironError):
    """Raised when ingestion or filtering fails in a domain-visible way."""

    code = codes.INGESTION_ERROR
    http_status = 500


class CrawlError(ChironError):
    """Raised when crawling sources fails."""

    code = codes.CRAWL_ERROR
    http_status = 500


# ---------------------------------------------------------------------------
# Auth / proxy errors
# ---------------------------------------------------------------------------

class AuthError(ChironError):
    """Raised for authentication or authorization failures."""

    code = codes.AUTH_ERROR
    http_status = 401


class ProxyError(ChironError):
    """Raised when the LLM proxy cannot reach the upstream model."""

    code = codes.PROXY_ERROR
    http_status = 502


# ---------------------------------------------------------------------------
# Validation / request errors
# ---------------------------------------------------------------------------

class ValidationError(ChironError):
    """Raised when request input is invalid."""

    code = codes.VALIDATION_ERROR
    http_status = 400


class NotFoundError(ChironError):
    """Raised when a requested resource does not exist."""

    code = codes.NOT_FOUND_ERROR
    http_status = 404


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
