"""Compatibility facade for canonical ChironAI error code constants."""

from core.contracts.errors import (
    AUTH_ERROR,
    CHIRON_ERROR,
    CRAWL_ERROR,
    EMBEDDING_ERROR,
    ERROR,
    INDEXING_ERROR,
    INGESTION_ERROR,
    NOT_FOUND_ERROR,
    PIPELINE_ERROR,
    PROXY_ERROR,
    RERANK_ERROR,
    RETRIEVAL_ERROR,
    VALIDATION_ERROR,
)

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
]
