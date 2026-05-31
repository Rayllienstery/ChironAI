"""
Domain services implement pure business rules.

Examples:
- Markdown metadata parsing shared by ingestion modules.

RAG services live under ``rag_service.domain.services``.
"""

from domain.services import markdown_meta

__all__ = ["markdown_meta"]
