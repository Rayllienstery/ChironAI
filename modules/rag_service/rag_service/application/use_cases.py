"""
RAG application use cases.

Orchestrates retrieval (embed, search, rerank) and chat using domain services
and injected ports (RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from rag_service.domain.entities import RagAnswerResponse, RagContext, RagQuestionRequest
from rag_service.domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from rag_service.domain.services.prompt_builder import (
    build_context_block,
    build_system_content,
    framework_filter,
    last_user_content,
)
from rag_service.domain.services.rerank import (
    apply_rerank_scores_and_cut,
    build_rerank_prompt,
    parse_rerank_order,
    reorder_hits_by_indices,
)
from rag_service.domain.services.retrieval import (
    FINAL_CONTEXT_K,
    MULTI_CHUNK_FINAL_K,
    MULTI_CHUNK_TOP_K,
    RERANK_MAX_CANDIDATES,
    build_qdrant_filter,
    combined_doc_priority,
    expand_query_variants,
    is_version_question,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
    rrf_merge_hit_lists,
    should_skip_rag_search,
)

try:
    from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector
except ImportError:
    def normalize_text_for_sparse(t: str) -> str:
        return " ".join((t or "").split())

    def text_to_sparse_vector(_t: str) -> tuple[list[int], list[float]]:
        return [], []

try:
    from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
except ImportError:
    try:
        from config import get_retrieval_bool

        def is_hybrid_sparse_enabled() -> bool:
            return bool(get_retrieval_bool("hybrid_sparse_enabled", True))
    except ImportError:

        def is_hybrid_sparse_enabled() -> bool:
            return True

_rag_log = logging.getLogger("rag_service.rag")

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
    timings: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    if not hits:
        return []
    candidates = hits[:RERANK_MAX_CANDIDATES]
    candidate_texts = [
        (idx, (h.get("payload") or {}).get("text", ""))
        for idx, h in enumerate(candidates, start=1)
    ]
    prompt_text = build_rerank_prompt(question, candidate_texts)
    if timings is not None:
        timings["rerank_prompt_tokens_in"] = timings.get("rerank_prompt_tokens_in", 0.0) + (
            0 if not prompt_text else max(1, int(len(prompt_text) / 4))
        )
    raw = rerank_client.rerank(question, prompt_text) if rerank_client else None
    order = parse_rerank_order(raw) if raw else None
    if order is not None:
        hits = reorder_hits_by_indices(candidates, order, hits)
    else:
        hits = list(hits)
    return apply_rerank_scores_and_cut(hits, final_k)


def _search_one(
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    search_query: str,
    top_k: int,
    filter_dict: dict[str, Any] | None,
    *,
    hybrid_on: bool,
    timings: dict[str, float],
) -> list[dict[str, Any]]:
    t0 = time.perf_counter()
    vec = embed_provider.embed(search_query)
    timings["embed_s"] += time.perf_counter() - t0
    timings["embed_tokens_in"] = timings.get("embed_tokens_in", 0.0) + (
        0 if not search_query else max(1, int(len(search_query) / 4))
    )
    si: list[int] | None = None
    sv: list[float] | None = None
    if hybrid_on:
        si, sv = text_to_sparse_vector(normalize_text_for_sparse(search_query))
        if not si:
            si, sv = None, None
    t0 = time.perf_counter()
    if si and sv:
        results = rag_repo.search(
            vec,
            top_k=top_k,
            filter_dict=filter_dict,
            sparse_indices=si,
            sparse_values=sv,
        )
    else:
        results = rag_repo.search(vec, top_k=top_k, filter_dict=filter_dict)
    if filter_dict and not results:
        if si and sv:
            results = rag_repo.search(
                vec,
                top_k=top_k,
                filter_dict=None,
                sparse_indices=si,
                sparse_values=sv,
            )
        else:
            results = rag_repo.search(vec, top_k=top_k, filter_dict=None)
    timings["search_s"] += time.perf_counter() - t0
    return results


def search_rag(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    top_k: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Run RAG retrieval: query_for_retrieval -> embed -> search -> rerank. Returns (hits, timings)."""
    timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "expand_variants_s": 0.0,
        "embed_tokens_in": 0.0,
        "rerank_prompt_tokens_in": 0.0,
    }
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", DEFAULT_TOP_K)
    hybrid_on = is_hybrid_sparse_enabled() and rag_repo.supports_hybrid()
    filter_dict = build_qdrant_filter(question)
    k = max(top_k, RERANK_MAX_CANDIDATES) if not is_version_question(question) else top_k
    final_k = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K

    if not is_version_question(question):
        t_exp0 = time.perf_counter()
        variants = expand_query_variants(question)
        timings["expand_variants_s"] += time.perf_counter() - t_exp0
        per_variant_k = max(4, min(k, max(4, k // max(1, len(variants)))))
        lists: list[list[dict[str, Any]]] = []
        for variant in variants:
            sq = query_for_retrieval(variant)
            lists.append(
                _search_one(
                    rag_repo,
                    embed_provider,
                    sq,
                    per_variant_k,
                    filter_dict,
                    hybrid_on=hybrid_on,
                    timings=timings,
                )
            )
        if len(lists) == 1:
            results = lists[0]
        else:
            results = rrf_merge_hit_lists(lists, limit=k)
        results.sort(key=combined_doc_priority, reverse=True)
        t0 = time.perf_counter()
        results = _apply_rerank(question, results, rerank_client, final_k, timings=timings)
        timings["rerank_s"] += time.perf_counter() - t0
        return results, timings
    search_query = query_for_retrieval(question)
    results = _search_one(
        rag_repo,
        embed_provider,
        search_query,
        k,
        filter_dict,
        hybrid_on=hybrid_on,
        timings=timings,
    )
    ios_q, swift_q = parse_versions_from_question(question)
    extra_results: list[dict[str, Any]] = []
    for v in swift_q:
        qv = f"Swift {v} version RELEASE"
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                qv,
                6,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                qv,
                6,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    if not extra_results:
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                "Swift version release number RELEASE",
                8,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
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
        results.sort(key=combined_doc_priority, reverse=True)
    t0 = time.perf_counter()
    results = _apply_rerank(question, results, rerank_client, final_k, timings=timings)
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
) -> tuple[RagContext, dict[str, float]]:
    """Build RAG context: search_rag -> framework_filter -> build_context_block."""
    empty_timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "expand_variants_s": 0.0,
        "total_rag_s": 0.0,
    }
    if not question or not question.strip():
        return RagContext("", [], 0.0), empty_timings
    if should_skip_rag_search(question):
        _rag_log.debug("RAG skipped for query (greeting or no RAG-required keyword)")
        return RagContext("", [], 0.0), empty_timings
    try:
        results, timings = search_rag(question, rag_repo, embed_provider, rerank_client, top_k=top_k)
        timings["total_rag_s"] = (
            timings["embed_s"]
            + timings["search_s"]
            + timings["rerank_s"]
            + timings.get("expand_variants_s", 0.0)
        )
        if not results:
            return RagContext("", [], 0.0), timings
        results = framework_filter(question, results)
        context_text, chunks_info, max_score = build_context_block(
            results, context_chunk_chars, context_total_chars
        )
        return RagContext(context_text=context_text, chunks_info=chunks_info, max_score=max_score), timings
    except Exception:
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
) -> RagAnswerResponse:
    """Answer a question with RAG: build_rag_context -> build_system_content -> chat."""
    last_user = last_user_content(request.messages)
    ctx, _ = build_rag_context(
        last_user, rag_repo, embed_provider, rerank_client,
        context_chunk_chars, context_total_chars,
    )
    system_content = build_system_content(
        system_prefix, system_suffix, ctx.context_text, ctx.max_score,
        confidence_threshold, reasoning_level, model_name,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            text = " ".join(p.get("text", "") for p in content) if isinstance(content, list) else (content or "")
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
) -> tuple[list[dict[str, Any]], str]:
    """Build RAG context and Ollama message list (for streaming or custom chat). Returns (ollama_messages, model)."""
    last_user = last_user_content(request.messages)
    ctx, _ = build_rag_context(
        last_user, rag_repo, embed_provider, rerank_client,
        context_chunk_chars, context_total_chars,
    )
    system_content = build_system_content(
        system_prefix, system_suffix, ctx.context_text, ctx.max_score,
        confidence_threshold, reasoning_level, model_name,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            text = " ".join(p.get("text", "") for p in content) if isinstance(content, list) else (content or "")
            ollama_messages.append({"role": role, "content": text})
    model = request.model or model_name
    return ollama_messages, model


__all__ = ["answer_question", "build_rag_context", "prepare_ollama_messages", "search_rag"]
