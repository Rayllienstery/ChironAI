"""Context assembly step for modular RAG core pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, MutableMapping

from rag_service.config import get_retrieval_int
from rag_service.core.contracts import StepResult
from rag_service.domain.entities import RagContext
from rag_service.domain.services.prompt_builder import build_context_block, framework_filter
from rag_service.domain.services.rag_trace import build_rag_trace_from_timings
from rag_service.domain.services.retrieval import (
    FINAL_CONTEXT_K,
    MULTI_CHUNK_FINAL_K,
    build_qdrant_filter,
    combined_doc_priority,
    compute_concept_coverage_report,
    intent_match_priority,
    merge_qdrant_filters,
    need_more_chunks,
    query_for_retrieval,
)

from rag_service.application.pipeline_steps.helpers import (
    build_rag_quality_from_report,
    coverage_trace_extra,
    finalize_reranked_hits,
    retrieval_bool_with_ui_override,
)

_rag_log = logging.getLogger("trag.rag")


class ContextAssemblyStep:
    """Build final context text and RagContext from retrieved hits."""

    id = "context_assembly"
    icon = "description"
    title = "Context assembly"
    description = "Apply coverage policies and build final RAG context block."
    depends_on = ("embed_search_pass1",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        # Local imports keep module encapsulation and avoid import-time cycles.
        from rag_service.application.use_cases import _apply_rerank, _search_one, is_hybrid_sparse_enabled

        question = str(ctx["question"])
        context_chunk_chars = int(ctx["context_chunk_chars"])
        context_total_chars = int(ctx["context_total_chars"])
        rag_repo = ctx["rag_repo"]
        embed_provider = ctx["embed_provider"]
        rerank_client = ctx.get("rerank_client")
        intent = ctx.get("intent")
        combined_extra_filter = ctx.get("combined_extra_filter")
        timings = dict(ctx.get("timings") or {})
        results = list(ctx.get("results") or [])
        rerank_pool = list(ctx.get("rerank_pool") or [])
        variants_n = int(ctx.get("variants_n") or 1)

        if not results:
            timings["total_rag_s"] = (
                timings.get("embed_s", 0.0)
                + timings.get("search_s", 0.0)
                + timings.get("pass2_embed_s", 0.0)
                + timings.get("pass2_search_s", 0.0)
                + timings.get("rerank_s", 0.0)
                + timings.get("expand_variants_s", 0.0)
                + timings.get("concept_expansion_prep_s", 0.0)
            )
            rag_trace = build_rag_trace_from_timings(
                timings, chunks_count=0, variants_count=variants_n
            )
            rag_context = RagContext("", [], 0.0, rag_trace=rag_trace)
            return StepResult(context_updates={"timings": timings, "rag_context": rag_context})

        results = framework_filter(question, results)
        pool = framework_filter(question, list(rerank_pool))
        fk = int(timings.get("final_context_k_used", 0) or 0)
        if fk <= 0:
            fk = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K

        report = compute_concept_coverage_report(question, results)
        gate_applied = False
        retry_search = False
        max_fk = get_retrieval_int("coverage_gate_max_final_k", 12)

        if retrieval_bool_with_ui_override("coverage_gate_enabled"):
            targets = report.get("target_concepts") or []
            ratio = report.get("coverage_ratio")
            min_ratio = get_retrieval_int("coverage_gate_min_percent", 75) / 100.0
            boost = max(0, get_retrieval_int("coverage_gate_boost_final_k", 2))
            if targets and ratio is not None and ratio < min_ratio and boost > 0:
                new_fk = min(fk + boost, max_fk, len(pool))
                if new_fk > fk:
                    results = finalize_reranked_hits(question, pool, new_fk)
                    fk = new_fk
                    timings["final_context_k_used"] = float(fk)
                    timings["coverage_gate_applied"] = 1.0
                    gate_applied = True
                    report = compute_concept_coverage_report(question, results)

        if retrieval_bool_with_ui_override("coverage_retry_supplemental_search_enabled"):
            targets = report.get("target_concepts") or []
            ratio = report.get("coverage_ratio")
            missing = list(report.get("missing_concepts") or [])
            min_ratio = get_retrieval_int("coverage_gate_min_percent", 75) / 100.0
            if targets and ratio is not None and ratio < min_ratio and missing:
                t_rs = time.perf_counter()
                retry_k = max(1, get_retrieval_int("coverage_retry_top_k", 6))
                max_m = max(1, get_retrieval_int("coverage_retry_max_missing_terms", 8))
                aug = " ".join(missing[:max_m])
                sq = query_for_retrieval(f"{question}\n{aug}")
                hybrid_on = is_hybrid_sparse_enabled() and rag_repo.supports_hybrid()
                filter_dict = merge_qdrant_filters(build_qdrant_filter(question), combined_extra_filter)
                extra_hits = _search_one(
                    rag_repo,
                    embed_provider,
                    sq,
                    retry_k,
                    filter_dict,
                    hybrid_on=hybrid_on,
                    timings=timings,
                )
                seen_ids = {h.get("id") for h in pool if h.get("id") is not None}
                for h in extra_hits:
                    hid = h.get("id")
                    if hid is not None and hid not in seen_ids:
                        seen_ids.add(hid)
                        pool.append(h)
                    elif hid is None:
                        pool.append(h)
                if intent is not None:
                    pool.sort(
                        key=lambda h: combined_doc_priority(h) + intent_match_priority(h, intent),
                        reverse=True,
                    )
                else:
                    pool.sort(key=combined_doc_priority, reverse=True)
                t_rr = time.perf_counter()
                pool = _apply_rerank(question, pool, rerank_client, timings=timings)
                timings["rerank_s"] += time.perf_counter() - t_rr
                retry_fk = get_retrieval_int("coverage_retry_final_k", 0)
                cap_fk = retry_fk if retry_fk > 0 else max_fk
                new_fk = min(max(fk, cap_fk), len(pool))
                results = finalize_reranked_hits(question, pool, new_fk)
                fk = new_fk
                timings["final_context_k_used"] = float(fk)
                timings["coverage_retry_search_s"] = time.perf_counter() - t_rs
                retry_search = True
                report = compute_concept_coverage_report(question, results)

        timings["total_rag_s"] = (
            timings.get("embed_s", 0.0)
            + timings.get("search_s", 0.0)
            + timings.get("pass2_embed_s", 0.0)
            + timings.get("pass2_search_s", 0.0)
            + timings.get("rerank_s", 0.0)
            + timings.get("expand_variants_s", 0.0)
            + timings.get("concept_expansion_prep_s", 0.0)
        )
        rag_quality = build_rag_quality_from_report(report)
        structured = retrieval_bool_with_ui_override("structured_rag_context_enabled")
        t_ca = time.perf_counter()
        context_text, chunks_info, max_score = build_context_block(
            results,
            context_chunk_chars,
            context_total_chars,
            structured=structured,
            question=question,
        )
        timings["context_assembly_s"] = time.perf_counter() - t_ca
        timings["total_rag_s"] += timings["context_assembly_s"]
        trace_extra = coverage_trace_extra(report, gate=gate_applied, retry_search=retry_search)
        rag_trace = build_rag_trace_from_timings(
            timings,
            chunks_count=len(chunks_info),
            variants_count=variants_n,
            context_assembly_extra=trace_extra,
        )
        count = len(chunks_info)
        if count:
            sources = list({c.get("doc_type") or "N/A" for c in chunks_info})
            _rag_log.debug(
                "RAG chunks count=%s max_score=%.2f sources=%s embed_s=%.2f search_s=%.2f rerank_s=%.2f total_rag_s=%.2f",
                count,
                max_score,
                ",".join(str(s) for s in sources[:5]),
                timings.get("embed_s", 0.0),
                timings.get("search_s", 0.0),
                timings.get("rerank_s", 0.0),
                timings.get("total_rag_s", 0.0),
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

        rag_context = RagContext(
            context_text=context_text,
            chunks_info=chunks_info,
            max_score=max_score,
            rag_trace=rag_trace,
            coverage_report=report,
            rag_quality=rag_quality,
        )
        return StepResult(
            context_updates={
                "timings": timings,
                "rag_context": rag_context,
            }
        )


__all__ = ["ContextAssemblyStep"]
