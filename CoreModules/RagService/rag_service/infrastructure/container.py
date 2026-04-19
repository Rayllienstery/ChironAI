"""RAG service composition root."""

from __future__ import annotations


from rag_service.infrastructure.ollama_chat import OllamaChatClient
from rag_service.infrastructure.ollama_embedding import OllamaEmbeddingProvider
from rag_service.infrastructure.ollama_rerank import OllamaRerankClient
from rag_service.infrastructure.qdrant_repository import QdrantRagRepository

from rag_service.config import (
    QDRANT_CONFIG,
    get_ollama_chat_model,
    get_ollama_chat_url,
    get_ollama_embed_url,
    get_ollama_generate_url,
    get_ollama_rerank_model,
    get_qdrant_url,
)


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
        explicit_collection=collection_name,
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
