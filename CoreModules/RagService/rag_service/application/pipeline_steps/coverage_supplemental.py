"""Coverage supplemental retrieval step."""

from __future__ import annotations

import time
from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.helpers import finalize_reranked_hits, retrieval_bool_with_ui_override
from rag_service.application.pipeline_steps.retrieval_flow import (
    apply_metadata_rank,
    apply_rerank,
    is_hybrid_sparse_enabled,
    search_one,
)
from rag_service.config import get_retrieval_int
from rag_service.core.contracts import StepResult
from rag_service.domain.services.retrieval import (
    build_qdrant_filter,
    compute_concept_coverage_report,
    merge_qdrant_filters,
    query_for_retrieval,
)


class CoverageSupplementalStep:
    id = "coverage_supplemental"
    icon = "library_add"
    title = "Coverage supplemental retrieval"
    description = "Run one supplemental retrieval pass for missing concepts and re-finalize."
    depends_on = ("coverage_gate",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        rag_repo = ctx["rag_repo"]
        embed_provider = ctx["embed_provider"]
        rerank_client = ctx.get("rerank_client")
        intent = ctx.get("intent")
        combined_extra_filter = ctx.get("combined_extra_filter")
        timings = dict(ctx.get("timings") or {})
        results = list(ctx.get("results") or [])
        pool = list(ctx.get("rerank_pool") or [])
        report = dict(ctx.get("coverage_report") or compute_concept_coverage_report(question, results))
        retry_search = False
        max_fk = get_retrieval_int("coverage_gate_max_final_k", 12)

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
                extra_hits = search_one(
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
                pool = apply_metadata_rank(pool, intent)
                t_rr = time.perf_counter()
                pool = apply_rerank(question, pool, rerank_client, timings=timings)
                timings["rerank_s"] += time.perf_counter() - t_rr
                fk = int(timings.get("final_context_k_used", 0) or 0)
                retry_fk = get_retrieval_int("coverage_retry_final_k", 0)
                cap_fk = retry_fk if retry_fk > 0 else max_fk
                new_fk = min(max(fk, cap_fk), len(pool))
                results = finalize_reranked_hits(question, pool, new_fk)
                timings["final_context_k_used"] = float(new_fk)
                timings["coverage_retry_search_s"] = time.perf_counter() - t_rs
                retry_search = True
                report = compute_concept_coverage_report(question, results)

        return StepResult(
            context_updates={
                "results": results,
                "rerank_pool": pool,
                "timings": timings,
                "coverage_report": report,
                "coverage_retry_search_flag": retry_search,
            }
        )


__all__ = ["CoverageSupplementalStep"]
