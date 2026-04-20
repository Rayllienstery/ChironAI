"""Rerank step for modular RAG pipeline."""

from __future__ import annotations

import time
from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.helpers import finalize_reranked_hits
from rag_service.application.pipeline_steps.retrieval_flow import apply_rerank
from rag_service.core.contracts import StepResult


class RerankStep:
    id = "rerank"
    icon = "swap_vert"
    title = "Cross-encoder rerank"
    description = "Rerank candidate chunks against full question and cut to final_k."
    depends_on = ("metadata_rank",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        rerank_client = ctx.get("rerank_client")
        timings = dict(ctx.get("timings") or {})
        candidate_results = list(ctx.get("candidate_results") or [])
        final_k = int(ctx.get("final_k") or 0)
        t0 = time.perf_counter()
        reranked = apply_rerank(question, candidate_results, rerank_client, timings=timings)
        rerank_pool = list(reranked)
        results = finalize_reranked_hits(question, rerank_pool, final_k if final_k > 0 else len(rerank_pool))
        timings["final_context_k_used"] = float(final_k if final_k > 0 else len(results))
        timings["rerank_s"] += time.perf_counter() - t0
        return StepResult(
            context_updates={
                "results": results,
                "rerank_pool": rerank_pool,
                "timings": timings,
            }
        )


__all__ = ["RerankStep"]
