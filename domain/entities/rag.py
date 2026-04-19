"""Compatibility wrapper to standalone rag_service entities."""

from rag_service.domain.entities import QueryIntent, RagAnswerResponse, RagChunk, RagContext, RagQuestionRequest

__all__ = ["RagChunk", "RagContext", "RagQuestionRequest", "RagAnswerResponse", "QueryIntent"]
