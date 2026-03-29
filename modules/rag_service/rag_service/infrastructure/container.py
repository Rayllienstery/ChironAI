"""
RAG service composition root.

Builds default infrastructure implementations. Requires project root on PYTHONPATH for config.
"""

from __future__ import annotations

import os

from rag_service.domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from rag_service.infrastructure.ollama_chat import OllamaChatClient
from rag_service.infrastructure.ollama_embedding import OllamaEmbeddingProvider
from rag_service.infrastructure.ollama_rerank import OllamaRerankClient
from rag_service.infrastructure.qdrant_repository import QdrantRagRepository

try:
    from config import (
        get_ollama_chat_model,
        get_ollama_chat_url,
        get_ollama_embed_url,
        get_ollama_generate_url,
        get_ollama_rerank_model,
        get_qdrant_url,
    )
    from config import QDRANT_CONFIG
except ImportError:
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore
    get_ollama_generate_url = lambda: "http://localhost:11434/api/generate"  # type: ignore
    get_ollama_chat_url = lambda: "http://localhost:11434/api/chat"  # type: ignore
    get_ollama_chat_model = lambda: "ChironAI-Worker"  # type: ignore
    get_ollama_rerank_model = lambda: "devstral-ios"  # type: ignore
    QDRANT_CONFIG = {}  # type: ignore


def default_rag_repository(
    collection_file: str | None = None,
    qdrant_url: str | None = None,
    default_collection: str | None = None,
    collection_name: str | None = None,
) -> QdrantRagRepository:
    collection = collection_name or default_collection or QDRANT_CONFIG.get("collection_name", "webcrawl")
    return QdrantRagRepository(
        base_url=qdrant_url or get_qdrant_url(),
        collection_file=collection_file,
        default_collection=collection,
    )


def default_embed_provider(
    embed_url: str | None = None,
    model: str | None = None,
) -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(base_url=embed_url or get_ollama_embed_url(), model=model)


def default_rerank_client(
    generate_url: str | None = None,
    model: str | None = None,
) -> OllamaRerankClient:
    return OllamaRerankClient(
        base_url=generate_url or get_ollama_generate_url(),
        model=model or get_ollama_rerank_model(),
    )


def default_chat_client(
    chat_url: str | None = None,
    model: str | None = None,
) -> OllamaChatClient:
    return OllamaChatClient(
        base_url=chat_url or get_ollama_chat_url(),
        model=model or get_ollama_chat_model(),
    )


__all__ = [
    "default_rag_repository",
    "default_embed_provider",
    "default_rerank_client",
    "default_chat_client",
]
