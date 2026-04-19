"""Compatibility wrapper to standalone rag_service use cases."""

from rag_service.application.use_cases import answer_question, build_rag_context, prepare_ollama_messages, search_rag

__all__ = ["answer_question", "build_rag_context", "prepare_ollama_messages", "search_rag"]
