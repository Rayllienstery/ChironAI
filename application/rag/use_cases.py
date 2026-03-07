"""
RAG application use cases.

Orchestrates retrieval (embed, search, rerank) and chat using domain services
and injected ports (RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from domain.entities.rag import RagAnswerResponse, RagContext, RagQuestionRequest
from domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from domain.services.prompt_builder import (
    build_context_block,
    build_system_content,
    framework_filter,
    last_user_content,
)
from domain.services.rerank import (
    apply_rerank_scores_and_cut,
    build_rerank_prompt,
    parse_rerank_order,
    reorder_hits_by_indices,
)
from domain.services.retrieval import (
    FINAL_CONTEXT_K,
    MULTI_CHUNK_FINAL_K,
    MULTI_CHUNK_TOP_K,
    RERANK_MAX_CANDIDATES,
    build_qdrant_filter,
    doc_type_priority,
    is_version_question,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
    should_skip_rag_search,
)

_rag_log = logging.getLogger("trag.rag")

try:
    from config import get_retrieval_int
except ImportError:
    get_retrieval_int = lambda k, d: d  # type: ignore
DEFAULT_TOP_K = 8


def _apply_rerank(
    question: str,
    hits: list[dict[str, Any]],
    rerank_client: RerankClient | None,
    final_k: int,
) -> list[dict[str, Any]]:
    """Apply LLM rerank and cut to final_k. Uses domain rerank logic + rerank_client."""
    if not hits:
        return []
    candidates = hits[:RERANK_MAX_CANDIDATES]
    candidate_texts = [
        (idx, (h.get("payload") or {}).get("text", ""))
        for idx, h in enumerate(candidates, start=1)
    ]
    prompt_text = build_rerank_prompt(question, candidate_texts)
    raw = rerank_client.rerank(question, prompt_text) if rerank_client else None
    order = parse_rerank_order(raw) if raw else None
    if order is not None:
        hits = reorder_hits_by_indices(candidates, order, hits)
    else:
        hits = list(hits)
    return apply_rerank_scores_and_cut(hits, final_k)


def search_rag(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    top_k: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Run RAG retrieval for a question: query_for_retrieval -> embed -> search -> rerank.
    Returns (list of hits with id, score, payload, rerank_score, timings dict with embed_s, search_s, rerank_s).
    """
    timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0}
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", DEFAULT_TOP_K)
    search_query = query_for_retrieval(question)
    t0 = time.perf_counter()
    vec = embed_provider.embed(search_query)
    timings["embed_s"] += time.perf_counter() - t0
    filter_dict = build_qdrant_filter(question)
    k = max(top_k, RERANK_MAX_CANDIDATES) if not is_version_question(question) else top_k
    t0 = time.perf_counter()
    results = rag_repo.search(vec, top_k=k, filter_dict=filter_dict)
    if filter_dict and not results:
        results = rag_repo.search(vec, top_k=k, filter_dict=None)
    timings["search_s"] += time.perf_counter() - t0
    final_k = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K
    if not is_version_question(question):
        results.sort(key=doc_type_priority, reverse=True)
        t0 = time.perf_counter()
        results = _apply_rerank(question, results, rerank_client, final_k)
        timings["rerank_s"] += time.perf_counter() - t0
        return results, timings
    ios_q, swift_q = parse_versions_from_question(question)
    extra_results: list[dict[str, Any]] = []
    for v in swift_q:
        qv = f"Swift {v} version RELEASE"
        t0 = time.perf_counter()
        vec_v = embed_provider.embed(qv)
        timings["embed_s"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        extra_results.extend(rag_repo.search(vec_v, top_k=6))
        timings["search_s"] += time.perf_counter() - t0
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        t0 = time.perf_counter()
        vec_v = embed_provider.embed(qv)
        timings["embed_s"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        extra_results.extend(rag_repo.search(vec_v, top_k=6))
        timings["search_s"] += time.perf_counter() - t0
    if not extra_results:
        t0 = time.perf_counter()
        vec_version = embed_provider.embed("Swift version release number RELEASE")
        timings["embed_s"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        extra_results.extend(rag_repo.search(vec_version, top_k=8))
        timings["search_s"] += time.perf_counter() - t0
    seen_ids = {r["id"] for r in results}
    for r in extra_results:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])
    ios_set = set(ios_q)
    swift_set = set(swift_q)

    def _score(h: dict[str, Any]) -> int:
        payload = h.get("payload") or {}
        ios_payload = set(payload.get("ios_versions") or [])
        swift_payload = set(payload.get("swift_versions") or [])
        s = 0
        if ios_set and ios_payload & ios_set:
            s += 3
        if swift_set and swift_payload & swift_set:
            s += 3
        if (ios_set or swift_set) and (ios_payload or swift_payload):
            s += 1
        return s

    if ios_set or swift_set:
        results.sort(key=_score, reverse=True)
        results.sort(key=doc_type_priority, reverse=True)
    t0 = time.perf_counter()
    results = _apply_rerank(question, results, rerank_client, final_k)
    timings["rerank_s"] += time.perf_counter() - t0
    return results, timings


def build_rag_context(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    context_chunk_chars: int,
    context_total_chars: int,
    top_k: int | None = None,
    rag_required_keywords: list[str] | None = None,
) -> tuple[RagContext, dict[str, float]]:
    """
    Build RAG context for a question: search_rag -> framework_filter -> build_context_block.
    Returns (RagContext (context_text, chunks_info, max_score), timings dict with embed_s, search_s, rerank_s, total_rag_s).
    If rag_required_keywords is provided, it is used to decide when to skip RAG (no keyword in query); else config default.
    """
    empty_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
    if not question or not question.strip():
        return RagContext("", [], 0.0), empty_timings
    if should_skip_rag_search(question, rag_required_keywords=rag_required_keywords):
        _rag_log.debug("RAG skipped for query (greeting or no RAG-required keyword)")
        return RagContext("", [], 0.0), empty_timings
    try:
        results, timings = search_rag(question, rag_repo, embed_provider, rerank_client, top_k=top_k)
        timings["total_rag_s"] = timings["embed_s"] + timings["search_s"] + timings["rerank_s"]
        if not results:
            return RagContext("", [], 0.0), timings
        results = framework_filter(question, results)
        context_text, chunks_info, max_score = build_context_block(
            results, context_chunk_chars, context_total_chars
        )
        count = len(chunks_info)
        if count:
            sources = list({c.get("doc_type") or "N/A" for c in chunks_info})
            _rag_log.info(
                "RAG chunks count=%s max_score=%.2f sources=%s embed_s=%.2f search_s=%.2f rerank_s=%.2f total_rag_s=%.2f",
                count,
                max_score,
                ",".join(str(s) for s in sources[:5]),
                timings["embed_s"],
                timings["search_s"],
                timings["rerank_s"],
                timings["total_rag_s"],
            )
            for c in chunks_info:
                _rag_log.debug(
                    "RAG chunk %s score=%s rerank=%s url=%s doc_type=%s",
                    c.get("index"),
                    c.get("score"),
                    c.get("rerank_score"),
                    (c.get("url") or "N/A")[:60],
                    c.get("doc_type") or "N/A",
                )
        return RagContext(context_text=context_text, chunks_info=chunks_info, max_score=max_score), timings
    except Exception as e:
        _rag_log.exception("RAG build_rag_context failed: %s", e)
        return RagContext("", [], 0.0), empty_timings


def answer_question(
    request: RagQuestionRequest,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    chat_client: ChatLLMClient,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: str | None = None,
    rag_required_keywords: list[str] | None = None,
    rag_context: RagContext | None = None,
) -> RagAnswerResponse:
    """
    Answer a question with RAG: build_rag_context (or use rag_context) -> build_system_content -> chat.
    Returns RagAnswerResponse (content, model, finish_reason).
    When rag_context is provided, RAG retrieval is skipped and the given context is used.
    """
    if rag_context is not None:
        ctx = rag_context
    else:
        last_user = last_user_content(request.messages)
        ctx, _ = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            rerank_client,
            context_chunk_chars,
            context_total_chars,
            rag_required_keywords=rag_required_keywords,
        )
    system_content = build_system_content(
        system_prefix,
        system_suffix,
        ctx.context_text,
        ctx.max_score,
        confidence_threshold,
        reasoning_level,
        model_name,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            if isinstance(content, list):
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
            else:
                text = content or ""
            ollama_messages.append({"role": role, "content": text})
    model = request.model or model_name
    content = chat_client.chat(ollama_messages, model, stream=False, options=None)
    return RagAnswerResponse(content=content, model=model, finish_reason="stop")


def prepare_ollama_messages(
    request: RagQuestionRequest,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: str | None = None,
    rag_required_keywords: list[str] | None = None,
    rag_context: RagContext | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Build RAG context (unless rag_context provided) and Ollama message list (for streaming or custom chat).
    Returns (ollama_messages, model).
    When rag_context is provided, RAG retrieval is skipped and the given context is used.
    """
    if rag_context is not None:
        ctx = rag_context
    else:
        last_user = last_user_content(request.messages)
        ctx, _ = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            rerank_client,
            context_chunk_chars,
            context_total_chars,
            rag_required_keywords=rag_required_keywords,
        )
    system_content = build_system_content(
        system_prefix,
        system_suffix,
        ctx.context_text,
        ctx.max_score,
        confidence_threshold,
        reasoning_level,
        model_name,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            if isinstance(content, list):
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
            else:
                text = content or ""
            ollama_messages.append({"role": role, "content": text})
    model = request.model or model_name
    return ollama_messages, model


__all__ = [
    "answer_question",
    "build_rag_context",
    "prepare_ollama_messages",
    "search_rag",
]
