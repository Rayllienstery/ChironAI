"""
RAG parameters and wired dependencies for CLI and HTTP.

Single place for prompt (prefix/suffix), context limits, confidence threshold,
model name, and wired dependencies. Requires project root on PYTHONPATH for config/prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from rag_service.domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient

from rag_service.config import get_default_chat_model, get_rag_float, get_rag_int, get_rag_system_prompt


class RAGAnswerParams(NamedTuple):
    """All parameters needed to run answer_question / prepare_ollama_messages."""

    system_prefix: str
    system_suffix: str
    context_chunk_chars: int
    context_total_chars: int
    confidence_threshold: float
    model_name: str
    log_preview_chars: int


@dataclass
class RAGDependencies:
    """Wired dependencies for RAG use cases."""

    rag_repo: RagRepository
    embed_provider: EmbeddingProvider
    rerank_client: RerankClient
    chat_client: ChatLLMClient


def wire_rag_use_cases(
    collection_file: str | None = None,
    webui_dir: str | None = None,
    collection_name: str | None = None,
) -> tuple[RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient]:
    """Return (rag_repo, embed_provider, rerank_client, chat_client). Uses rag_service infrastructure."""
    from rag_service.infrastructure.container import (  # noqa: PLC0415
        default_chat_client,
        default_embed_provider,
        default_rag_repository,
        default_rerank_client,
    )
    import os
    if collection_file is None and webui_dir:
        collection_file = os.path.join(webui_dir, "last_collection.txt")
    rag_repo = default_rag_repository(collection_file=collection_file, collection_name=collection_name)
    embed_provider = default_embed_provider()
    rerank_client = default_rerank_client()
    chat_client = default_chat_client()
    return rag_repo, embed_provider, rerank_client, chat_client


def get_rag_answer_params(
    webui_dir: str | None = None,
    collection_name: str | None = None,
    prompt_name: str | None = None,
) -> tuple[RAGAnswerParams, RAGDependencies]:
    """Return (params, deps) for RAG. Single source for prompt, config limits, and wired services."""
    prefix, suffix = get_rag_system_prompt(prompt_name)
    context_chunk_chars = get_rag_int("context_chunk_chars", 1000)
    context_total_chars = get_rag_int("context_total_chars", 7000)
    confidence_threshold = get_rag_float("confidence_threshold", 0.75)
    model_name = get_default_chat_model()
    log_preview_chars = get_rag_int("log_preview_chars", 800)
    params = RAGAnswerParams(
        system_prefix=prefix,
        system_suffix=suffix,
        context_chunk_chars=context_chunk_chars,
        context_total_chars=context_total_chars,
        confidence_threshold=confidence_threshold,
        model_name=model_name,
        log_preview_chars=log_preview_chars,
    )
    rag_repo, embed_provider, rerank_client, chat_client = wire_rag_use_cases(
        webui_dir=webui_dir, collection_name=collection_name
    )
    deps = RAGDependencies(
        rag_repo=rag_repo,
        embed_provider=embed_provider,
        rerank_client=rerank_client,
        chat_client=chat_client,
    )
    return params, deps


__all__ = ["RAGAnswerParams", "RAGDependencies", "get_rag_answer_params", "wire_rag_use_cases"]
