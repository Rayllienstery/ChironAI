"""RAG service composition root."""

from __future__ import annotations


from rag_service.infrastructure.ollama_chat import OllamaChatClient
from rag_service.infrastructure.ollama_embedding import OllamaEmbeddingProvider
from rag_service.infrastructure.ollama_rerank import OllamaRerankClient

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
) -> "QdrantRagRepository":
    # Deferred import: qdrant_client takes ~800ms to load and is only needed
    # when a RAG query is actually executed, not at server startup.
    from rag_service.infrastructure.qdrant_repository import QdrantRagRepository  # noqa: PLC0415

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
    runtime: object | None = None,
    runtime_getter: object | None = None,
    provider_id: str = "ollama",
) -> object:
    legacy = OllamaEmbeddingProvider(base_url=embed_url or get_ollama_embed_url(), model=model)
    if runtime is None and runtime_getter is None:
        return legacy
    from rag_service.infrastructure.provider_runtime import RuntimeBackedEmbeddingProvider  # noqa: PLC0415

    return RuntimeBackedEmbeddingProvider(
        runtime=runtime,
        runtime_getter=runtime_getter,  # type: ignore[arg-type]
        provider_id=provider_id,
        model=model,
        delegate=legacy,
    )


def default_rerank_client(
    generate_url: str | None = None,
    model: str | None = None,
    runtime: object | None = None,
    runtime_getter: object | None = None,
    provider_id: str = "ollama",
) -> object:
    legacy = OllamaRerankClient(
        base_url=generate_url or get_ollama_generate_url(),
        model=model or get_ollama_rerank_model(),
    )
    if runtime is None and runtime_getter is None:
        return legacy
    from rag_service.infrastructure.provider_runtime import RuntimeBackedRerankClient  # noqa: PLC0415

    return RuntimeBackedRerankClient(
        runtime=runtime,
        runtime_getter=runtime_getter,  # type: ignore[arg-type]
        provider_id=provider_id,
        model=model or get_ollama_rerank_model(),
        delegate=legacy,
    )


def default_chat_client(
    chat_url: str | None = None,
    model: str | None = None,
    runtime: object | None = None,
    provider_id: str = "ollama",
) -> object:
    legacy = OllamaChatClient(
        base_url=chat_url or get_ollama_chat_url(),
        model=model or get_ollama_chat_model(),
    )
    if runtime is None:
        return legacy
    from llm_interactor import RuntimeBackedChatClient  # noqa: PLC0415

    return RuntimeBackedChatClient(
        runtime,  # type: ignore[arg-type]
        provider_id=provider_id,
        upstream_url=getattr(legacy, "_url", None),
        default_options=getattr(legacy, "_default_options", None),
        delegate=legacy,
    )


__all__ = [
    "default_rag_repository",
    "default_embed_provider",
    "default_rerank_client",
    "default_chat_client",
]
