"""Shared retrieval flow helpers for modular RAG steps."""

from __future__ import annotations

import time
from typing import Any

from rag_service.config import get_retrieval_bool, get_retrieval_int
from rag_service.domain.entities import QueryIntent
from rag_service.domain.ports import EmbeddingProvider, RagRepository, RerankClient
from rag_service.domain.services.rerank import (
    assign_rerank_scores,
    build_rerank_prompt,
    parse_rerank_order,
    reorder_hits_by_indices,
)
from rag_service.domain.services.retrieval import (
    FINAL_CONTEXT_K,
    MULTI_CHUNK_FINAL_K,
    RERANK_MAX_CANDIDATES,
    build_qdrant_filter,
    build_secondary_retrieval_query,
    combined_doc_priority,
    expand_concepts_with_map,
    expand_query_variants,
    extract_symbols_from_pass1_hits,
    extract_target_concepts_for_coverage,
    intent_match_priority,
    is_version_question,
    merge_qdrant_filters,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
    rrf_merge_hit_lists,
    source_authority_priority,
)
from rag_service.infrastructure.sparse_text import normalize_text_for_sparse, text_to_sparse_vector


def is_hybrid_sparse_enabled() -> bool:
    return get_retrieval_bool("hybrid_sparse_enabled", True)


def init_retrieval_timings() -> dict[str, float]:
    return {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "expand_variants_s": 0.0,
        "pass2_embed_s": 0.0,
        "pass2_search_s": 0.0,
        "concept_expansion_prep_s": 0.0,
        "concept_expansion_pass2_ran": 0.0,
        "concept_expansion_pass2_new_hits": 0.0,
        "retrieval_candidates_n": 0.0,
        "query_variants_count": 1.0,
        "context_assembly_s": 0.0,
        "embed_tokens_in": 0.0,
        "rerank_prompt_tokens_in": 0.0,
        "final_context_k_used": 0.0,
        "coverage_gate_applied": 0.0,
        "coverage_retry_search_s": 0.0,
    }


def search_one(
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    search_query: str,
    top_k: int,
    filter_dict: dict[str, Any] | None,
    *,
    hybrid_on: bool,
    timings: dict[str, float],
    embed_key: str = "embed_s",
    search_key: str = "search_s",
) -> list[dict[str, Any]]:
    t0 = time.perf_counter()
    vec = embed_provider.embed(search_query)
    timings[embed_key] = timings.get(embed_key, 0.0) + time.perf_counter() - t0
    timings["embed_tokens_in"] += 0 if not search_query else max(1, int(len(search_query) / 4))
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
    timings[search_key] = timings.get(search_key, 0.0) + time.perf_counter() - t0
    return results


def apply_metadata_rank(results: list[dict[str, Any]], intent: QueryIntent | None) -> list[dict[str, Any]]:
    ranked = list(results)
    if intent is not None:
        ranked.sort(
            key=lambda h: (
                combined_doc_priority(h)
                + intent_match_priority(h, intent)
                + source_authority_priority(h, intent)
            ),
            reverse=True,
        )
    else:
        ranked.sort(key=combined_doc_priority, reverse=True)
    return ranked


def retrieve_pass1_candidates(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    *,
    top_k: int,
    extra_filter: dict[str, Any] | None,
    timings: dict[str, float],
) -> tuple[list[dict[str, Any]], int]:
    hybrid_on = is_hybrid_sparse_enabled() and rag_repo.supports_hybrid()
    filter_dict = merge_qdrant_filters(build_qdrant_filter(question), extra_filter)
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
                search_one(
                    rag_repo,
                    embed_provider,
                    sq,
                    per_variant_k,
                    filter_dict,
                    hybrid_on=hybrid_on,
                    timings=timings,
                )
            )
        results = lists[0] if len(lists) == 1 else rrf_merge_hit_lists(lists, limit=k)
        timings["query_variants_count"] = float(len(variants))
        timings["retrieval_candidates_n"] = float(len(results))
        return results, final_k

    search_query = query_for_retrieval(question)
    results = search_one(
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
            search_one(rag_repo, embed_provider, qv, 6, filter_dict, hybrid_on=hybrid_on, timings=timings)
        )
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        extra_results.extend(
            search_one(rag_repo, embed_provider, qv, 6, filter_dict, hybrid_on=hybrid_on, timings=timings)
        )
    if not extra_results:
        extra_results.extend(
            search_one(
                rag_repo,
                embed_provider,
                "Swift version release number RELEASE",
                8,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    seen_ids = {r.get("id") for r in results}
    for r in extra_results:
        rid = r.get("id")
        if rid not in seen_ids:
            results.append(r)
            seen_ids.add(rid)
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
    timings["query_variants_count"] = 1.0
    timings["retrieval_candidates_n"] = float(len(results))
    return results, final_k


def maybe_apply_concept_expansion(
    question: str,
    results: list[dict[str, Any]],
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    *,
    extra_filter: dict[str, Any] | None,
    timings: dict[str, float],
) -> list[dict[str, Any]]:
    if not retrieval_bool_with_ui_override("concept_expansion_enabled"):
        return list(results)
    if is_version_question(question):
        return list(results)
    t_prep = time.perf_counter()
    seed_n = get_retrieval_int("concept_expansion_seed_hits", 4)
    seeds: list[str] = []
    seen_seed: set[str] = set()
    for x in extract_target_concepts_for_coverage(question):
        xl = (x or "").strip().lower()
        if xl and xl not in seen_seed:
            seen_seed.add(xl)
            seeds.append(xl)
    for x in extract_symbols_from_pass1_hits(results, seed_n):
        if x not in seen_seed:
            seen_seed.add(x)
            seeds.append(x)
    expanded = expand_concepts_with_map(seeds)
    timings["concept_expansion_prep_s"] = time.perf_counter() - t_prep
    if not expanded:
        return list(results)
    sq2 = build_secondary_retrieval_query(question, expanded)
    pass2_k = get_retrieval_int("concept_expansion_pass2_top_k", 8)
    hybrid_on = is_hybrid_sparse_enabled() and rag_repo.supports_hybrid()
    filter_dict = merge_qdrant_filters(build_qdrant_filter(question), extra_filter)
    p2 = search_one(
        rag_repo,
        embed_provider,
        sq2,
        pass2_k,
        filter_dict,
        hybrid_on=hybrid_on,
        timings=timings,
        embed_key="pass2_embed_s",
        search_key="pass2_search_s",
    )
    out = list(results)
    seen_ids = {h.get("id") for h in out}
    added = 0
    for h in p2:
        hid = h.get("id")
        if hid is not None and hid not in seen_ids:
            seen_ids.add(hid)
            out.append(h)
            added += 1
    timings["concept_expansion_pass2_ran"] = 1.0
    timings["concept_expansion_pass2_new_hits"] = float(added)
    return out


def apply_rerank(
    question: str,
    hits: list[dict[str, Any]],
    rerank_client: RerankClient | None,
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
        ranked = reorder_hits_by_indices(candidates, order, hits)
    else:
        ranked = list(hits)
    assign_rerank_scores(ranked)
    return ranked


def retrieval_bool_with_ui_override(key: str, *, yaml_fallback: bool = False) -> bool:
    return get_retrieval_bool(key, yaml_fallback)


__all__ = [
    "apply_metadata_rank",
    "apply_rerank",
    "init_retrieval_timings",
    "is_hybrid_sparse_enabled",
    "maybe_apply_concept_expansion",
    "retrieve_pass1_candidates",
    "search_one",
]
