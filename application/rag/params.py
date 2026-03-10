"""
Unified RAG parameters and wiring for CLI and HTTP proxy.

Single place for: prompt (prefix/suffix), context limits, confidence threshold,
model name, and wired dependencies (rag_repo, embed_provider, rerank_client, chat_client).
Used by rag_client.py and api.http.rag_routes so both share the same logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NamedTuple

from application.container import wire_rag_use_cases
from domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient

try:
    from config import get_ollama_chat_model, get_rag_float, get_rag_int
    from config.rag_prompts import get_rag_system_prompt
except ImportError:
    get_rag_int = lambda k, d: d  # type: ignore
    get_rag_float = lambda k, d: d  # type: ignore
    get_ollama_chat_model = lambda: "rag-ollama"  # type: ignore
    get_rag_system_prompt = lambda prompt_name=None: ("", "\n=================================\n")  # type: ignore


class RAGAnswerParams(NamedTuple):
    """All parameters needed to run answer_question / prepare_ollama_messages."""

    system_prefix: str
    system_suffix: str
    context_chunk_chars: int
    context_total_chars: int
    confidence_threshold: float
    model_name: str
    log_preview_chars: int  # for HTTP logging only; CLI may ignore


@dataclass
class RAGDependencies:
    """Wired dependencies for RAG use cases."""

    rag_repo: RagRepository
    embed_provider: EmbeddingProvider
    rerank_client: RerankClient
    chat_client: ChatLLMClient


def get_rag_answer_params(
    webui_dir: str | None = None,
    collection_name: str | None = None,
    prompt_name: str | None = None,
) -> tuple[RAGAnswerParams, RAGDependencies]:
    """
    Return (params, rag_repo, embed_provider, rerank_client, chat_client) for RAG.

    Single source for prompt, config limits, and wired services. Use this in
    rag_client and rag_routes so search, filtering, and chunk handling stay unified.

    Args:
        webui_dir: Optional WebUI directory hint for wiring dependencies.
        collection_name: Explicit Qdrant collection name to use for RAG retrieval.
        prompt_name: Optional system prompt name override (stem of prompts/*.md).
            When None, config default is used (same behavior as before).
    """
    prefix, suffix = get_rag_system_prompt(prompt_name)
    context_chunk_chars = get_rag_int("context_chunk_chars", 1000)
    context_total_chars = get_rag_int("context_total_chars", 7000)
    confidence_threshold = get_rag_float("confidence_threshold", 0.75)
    model_name = get_ollama_chat_model()
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
    rag_repo, embed_provider, rerank_client, chat_client = wire_rag_use_cases(webui_dir=webui_dir, collection_name=collection_name)
    deps = RAGDependencies(
        rag_repo=rag_repo,
        embed_provider=embed_provider,
        rerank_client=rerank_client,
        chat_client=chat_client,
    )
    return params, deps


__all__ = ["RAGAnswerParams", "RAGDependencies", "get_rag_answer_params"]
