"""
Application composition root.

Wires default infrastructure implementations to ports and exposes
use-case dependencies (e.g. for RAG). Presentation layer imports from here
or from use_cases with pre-wired dependencies.
"""

from __future__ import annotations

import os

from domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient

try:
    from config import (
        get_ollama_chat_model,
        get_ollama_chat_url,
        get_ollama_embed_url,
        get_ollama_generate_url,
        get_ollama_rerank_model,
        get_qdrant_url,
    )
except ImportError:
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore
    get_ollama_generate_url = lambda: "http://localhost:11434/api/generate"  # type: ignore
    get_ollama_chat_url = lambda: "http://localhost:11434/api/chat"  # type: ignore
    get_ollama_chat_model = lambda: "rag-ollama"  # type: ignore
    get_ollama_rerank_model = lambda: "devstral-ios"  # type: ignore

from infrastructure.fs.markdown_store import FileMarkdownStore
from infrastructure.ollama.chat_client import OllamaChatClient
from infrastructure.ollama.embed_client import OllamaEmbeddingProvider
from infrastructure.ollama.rerank_client import OllamaRerankClient
from infrastructure.qdrant.rag_repository_impl import QdrantRagRepository


def default_rag_repository(
    collection_file: str | None = None,
    qdrant_url: str | None = None,
    default_collection: str = "webcrawl",
) -> QdrantRagRepository:
    """Build default RagRepository (Qdrant)."""
    return QdrantRagRepository(
        base_url=qdrant_url or get_qdrant_url(),
        collection_file=collection_file,
        default_collection=default_collection,
    )


def default_embed_provider(
    embed_url: str | None = None,
    model: str | None = None,
) -> OllamaEmbeddingProvider:
    """Build default EmbeddingProvider (Ollama)."""
    return OllamaEmbeddingProvider(
        base_url=embed_url or get_ollama_embed_url(),
        model=model,
    )


def default_rerank_client(
    generate_url: str | None = None,
    model: str | None = None,
) -> OllamaRerankClient:
    """Build default RerankClient (Ollama generate)."""
    return OllamaRerankClient(
        base_url=generate_url or get_ollama_generate_url(),
        model=model or get_ollama_rerank_model(),
    )


def default_chat_client(
    chat_url: str | None = None,
    model: str | None = None,
) -> OllamaChatClient:
    """Build default ChatLLMClient (Ollama chat)."""
    return OllamaChatClient(
        base_url=chat_url or get_ollama_chat_url(),
        model=model or get_ollama_chat_model(),
    )


def default_markdown_store(base_dir: str) -> FileMarkdownStore:
    """Build default MarkdownStore (filesystem)."""
    return FileMarkdownStore(base_dir)


def wire_rag_use_cases(
    collection_file: str | None = None,
    webui_dir: str | None = None,
) -> tuple[RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient]:
    """
    Return (rag_repo, embed_provider, rerank_client, chat_client) for RAG use cases.
    If collection_file is None and webui_dir is set, uses webui_dir/last_collection.txt.
    """
    if collection_file is None and webui_dir:
        collection_file = os.path.join(webui_dir, "last_collection.txt")
    rag_repo = default_rag_repository(collection_file=collection_file)
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
