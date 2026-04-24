"""Compat wrapper for canonical ``rag_service.infrastructure.container``.

This module stays intentionally thin. The only local helpers are
``default_markdown_store`` and ``wire_rag_use_cases`` for legacy root-package
callers that still expect these convenience entry points.
"""

from __future__ import annotations

from os import path as os_path

from domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from infrastructure.fs.markdown_store import FileMarkdownStore
from rag_service.infrastructure.container import (
    default_chat_client,
    default_embed_provider,
    default_rag_repository,
    default_rerank_client,
)


def default_markdown_store(base_dir: str) -> FileMarkdownStore:
    """Build default MarkdownStore (filesystem)."""
    return FileMarkdownStore(base_dir)


def wire_rag_use_cases(
    collection_file: str | None = None,
    webui_dir: str | None = None,
    collection_name: str | None = None,
) -> tuple[RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient]:
    """Return pre-wired legacy root-package RAG dependencies."""
    if collection_file is None and webui_dir:
        collection_file = os_path.join(webui_dir, "last_collection.txt")
    rag_repo = default_rag_repository(collection_file=collection_file, collection_name=collection_name)
    embed_provider = default_embed_provider()
    rerank_client = default_rerank_client()
    chat_client = default_chat_client()
    return rag_repo, embed_provider, rerank_client, chat_client


__all__ = [
    "default_chat_client",
    "default_embed_provider",
    "default_markdown_store",
    "default_rag_repository",
    "default_rerank_client",
    "wire_rag_use_cases",
]
