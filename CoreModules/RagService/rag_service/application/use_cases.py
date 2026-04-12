"""
RAG application use cases for the ``rag_service`` package.

Canonical implementation: ``application.rag.use_cases`` (monorepo root). This module
re-exports the same functions so standalone HTTP and imports keep working when the
project root is on ``PYTHONPATH``.
"""

from __future__ import annotations

from application.rag.use_cases import (
    answer_question,
    build_rag_context,
    prepare_ollama_messages,
    search_rag,
)

__all__ = [
    "answer_question",
    "build_rag_context",
    "prepare_ollama_messages",
    "search_rag",
]
