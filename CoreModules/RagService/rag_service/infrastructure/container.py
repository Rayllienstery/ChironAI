"""RAG service composition root."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rag_service.config import QDRANT_CONFIG, get_qdrant_url
from rag_service.infrastructure.runtime_hooks import get_llm_runtime_getter

if TYPE_CHECKING:
    from rag_service.infrastructure.qdrant_repository import QdrantRagRepository


def _resolve_runtime_getter(
    runtime: Any | None,
    runtime_getter: Callable[[], Any | None] | None,
) -> Callable[[], Any | None]:
    if runtime is not None:
        return lambda: runtime
    if runtime_getter is not None:
        return runtime_getter
    hook = get_llm_runtime_getter()
    if hook is not None:
        return hook
    return lambda: None


def default_rag_repository(
    collection_file: str | None = None,
    qdrant_url: str | None = None,
    default_collection: str | None = None,
    collection_name: str | None = None,
) -> QdrantRagRepository:
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
    del embed_url  # extension runtime owns upstream URLs
    from rag_service.infrastructure.provider_runtime import RuntimeBackedEmbeddingProvider  # noqa: PLC0415

    return RuntimeBackedEmbeddingProvider(
        runtime_getter=_resolve_runtime_getter(runtime, runtime_getter),  # type: ignore[arg-type]
        provider_id=provider_id,
        model=model,
    )


def default_rerank_client(
    generate_url: str | None = None,
    model: str | None = None,
    runtime: object | None = None,
    runtime_getter: object | None = None,
    provider_id: str = "ollama",
) -> object:
    del generate_url
    from rag_service.infrastructure.provider_runtime import RuntimeBackedRerankClient  # noqa: PLC0415

    return RuntimeBackedRerankClient(
        runtime_getter=_resolve_runtime_getter(runtime, runtime_getter),  # type: ignore[arg-type]
        provider_id=provider_id,
        model=model,
    )


def default_chat_client(
    chat_url: str | None = None,
    model: str | None = None,
    runtime: object | None = None,
    runtime_getter: object | None = None,
    provider_id: str = "ollama",
) -> object:
    del chat_url
    from rag_service.infrastructure.provider_runtime import RuntimeResolvingChatClient  # noqa: PLC0415

    return RuntimeResolvingChatClient(
        runtime_getter=_resolve_runtime_getter(runtime, runtime_getter),  # type: ignore[arg-type]
        provider_id=provider_id,
        model=model,
    )


__all__ = [
    "default_rag_repository",
    "default_embed_provider",
    "default_rerank_client",
    "default_chat_client",
]
