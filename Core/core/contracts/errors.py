"""Shared ChironAI error contract and canonical error codes."""

from __future__ import annotations

from typing import Any

# Generic
ERROR = "ERROR"
CHIRON_ERROR = "CHIRON_ERROR"

# RAG / retrieval pipeline
RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
EMBEDDING_ERROR = "EMBEDDING_ERROR"
RERANK_ERROR = "RERANK_ERROR"
PIPELINE_ERROR = "PIPELINE_ERROR"

# Ingestion / crawling
INDEXING_ERROR = "INDEXING_ERROR"
INGESTION_ERROR = "INGESTION_ERROR"
CRAWL_ERROR = "CRAWL_ERROR"

# Auth / proxy
AUTH_ERROR = "AUTH_ERROR"
PROXY_ERROR = "PROXY_ERROR"

# Validation
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND_ERROR = "NOT_FOUND_ERROR"


class ChironError(Exception):
    """Base class for all ChironAI domain errors."""

    code: str = CHIRON_ERROR
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
        data: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            data["details"] = self.details
        return data

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class RetrievalError(ChironError):
    """Raised when RAG retrieval fails in a domain-visible way."""

    code = RETRIEVAL_ERROR
    http_status = 502


class EmbeddingError(ChironError):
    """Raised when embedding generation fails."""

    code = EMBEDDING_ERROR
    http_status = 502


class RerankError(ChironError):
    """Raised when reranking cannot be completed."""

    code = RERANK_ERROR
    http_status = 502


class PipelineError(ChironError):
    """Raised when a RAG pipeline step fails fatally."""

    code = PIPELINE_ERROR
    http_status = 500


class IndexingError(ChironError):
    """Raised when indexing content into the vector store fails."""

    code = INDEXING_ERROR
    http_status = 500


class IngestionError(ChironError):
    """Raised when ingestion or filtering fails in a domain-visible way."""

    code = INGESTION_ERROR
    http_status = 500


class CrawlError(ChironError):
    """Raised when crawling sources fails."""

    code = CRAWL_ERROR
    http_status = 500


class AuthError(ChironError):
    """Raised for authentication or authorization failures."""

    code = AUTH_ERROR
    http_status = 401


class ProxyError(ChironError):
    """Raised when the LLM proxy cannot reach the upstream model."""

    code = PROXY_ERROR
    http_status = 502


class ValidationError(ChironError):
    """Raised when request input is invalid."""

    code = VALIDATION_ERROR
    http_status = 400


class NotFoundError(ChironError):
    """Raised when a requested resource does not exist."""

    code = NOT_FOUND_ERROR
    http_status = 404


__all__ = [
    "ERROR",
    "CHIRON_ERROR",
    "RETRIEVAL_ERROR",
    "EMBEDDING_ERROR",
    "RERANK_ERROR",
    "PIPELINE_ERROR",
    "INDEXING_ERROR",
    "INGESTION_ERROR",
    "CRAWL_ERROR",
    "AUTH_ERROR",
    "PROXY_ERROR",
    "VALIDATION_ERROR",
    "NOT_FOUND_ERROR",
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
