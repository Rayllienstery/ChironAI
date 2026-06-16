"""Compat shim to canonical ``rag_service.infrastructure.qdrant_repository``.

This module is a legacy entry point for the RAG repository implementation.
The canonical implementation has been moved to the `rag_service` package
as part of the modularization effort.

Deprecation Plan:
    This shim will be removed in v0.8.0. Callers should migrate to
    `from rag_service.infrastructure.qdrant_repository import QdrantRagRepository`.
"""

from rag_service.infrastructure.qdrant_repository import QdrantRagRepository

__all__ = ["QdrantRagRepository"]
