"""Primary retrieval step for modular RAG core pipeline."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.core.contracts import StepResult
from rag_service.application.pipeline_steps.retrieval_flow import init_retrieval_timings, retrieve_pass1_candidates


class EmbedSearchPass1Step:
    """
    Run retrieval through existing search_rag orchestration.

    In PR-2 this step delegates to existing retrieval implementation to preserve parity
    while moving orchestration boundaries into RagCore.
    """

    id = "embed_search_pass1"
    icon = "database"
    title = "Embedding and first retrieval"
    description = "Run embedding + vector search and produce rerank pool."
    depends_on = ("query_prep",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        rag_repo = ctx["rag_repo"]
        embed_provider = ctx["embed_provider"]
        resolved_top_k = int(ctx["resolved_top_k"])
        combined_extra_filter = ctx.get("combined_extra_filter")
        timings = init_retrieval_timings()
        results, final_k = retrieve_pass1_candidates(
            question,
            rag_repo,
            embed_provider,
            top_k=resolved_top_k,
            extra_filter=combined_extra_filter,
            timings=timings,
        )
        return StepResult(
            context_updates={
                "candidate_results": results,
                "timings": timings,
                "final_k": int(final_k),
                "variants_n": int(timings.get("query_variants_count", 1) or 1),
            }
        )


__all__ = ["EmbedSearchPass1Step"]
