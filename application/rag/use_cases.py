"""
RAG application use cases.

Orchestrates retrieval (embed, search, rerank) and chat using domain services
and injected ports (RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

from domain.entities.rag import RagAnswerResponse, RagContext, RagQuestionRequest

_rag_log = logging.getLogger("trag.rag")
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
)

try:
    from config import get_retrieval_int
except ImportError:
    get_retrieval_int = lambda k, d: d  # type: ignore
DEFAULT_TOP_K = 8


def _apply_rerank(
    question: str,
    hits: List[Dict[str, Any]],
    rerank_client: Any,
    final_k: int,
) -> List[Dict[str, Any]]:
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
    rag_repo: Any,
    embed_provider: Any,
    rerank_client: Any,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Run RAG retrieval for a question: query_for_retrieval -> embed -> search -> rerank.
    Returns list of hits with id, score, payload, rerank_score.
    """
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", DEFAULT_TOP_K)
    search_query = query_for_retrieval(question)
    vec = embed_provider.embed(search_query)
    filter_dict = build_qdrant_filter(question)
    k = max(top_k, RERANK_MAX_CANDIDATES) if not is_version_question(question) else top_k
    results = rag_repo.search(vec, top_k=k, filter_dict=filter_dict)
    if filter_dict and not results:
        results = rag_repo.search(vec, top_k=k, filter_dict=None)
    final_k = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K
    if not is_version_question(question):
        results.sort(key=doc_type_priority, reverse=True)
        return _apply_rerank(question, results, rerank_client, final_k)
    ios_q, swift_q = parse_versions_from_question(question)
    extra_results: List[Dict[str, Any]] = []
    for v in swift_q:
        qv = f"Swift {v} version RELEASE"
        vec_v = embed_provider.embed(qv)
        extra_results.extend(rag_repo.search(vec_v, top_k=6))
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        vec_v = embed_provider.embed(qv)
        extra_results.extend(rag_repo.search(vec_v, top_k=6))
    if not extra_results:
        vec_version = embed_provider.embed("Swift version release number RELEASE")
        extra_results.extend(rag_repo.search(vec_version, top_k=8))
    seen_ids = {r["id"] for r in results}
    for r in extra_results:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])
    ios_set = set(ios_q)
    swift_set = set(swift_q)

    def _score(h: Dict[str, Any]) -> int:
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
    return _apply_rerank(question, results, rerank_client, final_k)


def build_rag_context(
    question: str,
    rag_repo: Any,
    embed_provider: Any,
    rerank_client: Any,
    context_chunk_chars: int,
    context_total_chars: int,
) -> RagContext:
    """
    Build RAG context for a question: search_rag -> framework_filter -> build_context_block.
    Returns RagContext (context_text, chunks_info, max_score).
    """
    if not question or not question.strip():
        return RagContext("", [], 0.0)
    try:
        results = search_rag(question, rag_repo, embed_provider, rerank_client)
        if not results:
            return RagContext("", [], 0.0)
        results = framework_filter(question, results)
        context_text, chunks_info, max_score = build_context_block(
            results, context_chunk_chars, context_total_chars
        )
        count = len(chunks_info)
        if count:
            sources = list({c.get("doc_type") or "N/A" for c in chunks_info})
            _rag_log.info(
                "RAG chunks count=%s max_score=%.2f sources=%s",
                count,
                max_score,
                ",".join(str(s) for s in sources[:5]),
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
        return RagContext(context_text=context_text, chunks_info=chunks_info, max_score=max_score)
    except Exception:
        return RagContext("", [], 0.0)


def answer_question(
    request: RagQuestionRequest,
    rag_repo: Any,
    embed_provider: Any,
    rerank_client: Any,
    chat_client: Any,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: Optional[str] = None,
) -> RagAnswerResponse:
    """
    Answer a question with RAG: build_rag_context -> build_system_content -> chat.
    Returns RagAnswerResponse (content, model, finish_reason).
    """
    last_user = last_user_content(request.messages)
    ctx = build_rag_context(
        last_user,
        rag_repo,
        embed_provider,
        rerank_client,
        context_chunk_chars,
        context_total_chars,
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
    rag_repo: Any,
    embed_provider: Any,
    rerank_client: Any,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build RAG context and Ollama message list (for streaming or custom chat).
    Returns (ollama_messages, model).
    """
    last_user = last_user_content(request.messages)
    ctx = build_rag_context(
        last_user,
        rag_repo,
        embed_provider,
        rerank_client,
        context_chunk_chars,
        context_total_chars,
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
