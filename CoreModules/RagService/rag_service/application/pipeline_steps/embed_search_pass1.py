"""Primary retrieval step for modular RAG core pipeline."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.core.contracts import StepResult


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
        # Local import to avoid broad module coupling at import-time.
        from rag_service.application.use_cases import search_rag

        question = str(ctx["question"])
        rag_repo = ctx["rag_repo"]
        embed_provider = ctx["embed_provider"]
        rerank_client = ctx.get("rerank_client")
        resolved_top_k = int(ctx["resolved_top_k"])
        combined_extra_filter = ctx.get("combined_extra_filter")
        intent = ctx.get("intent")

        results, timings, rerank_pool = search_rag(
            question,
            rag_repo,
            embed_provider,
            rerank_client,
            top_k=resolved_top_k,
            extra_filter=combined_extra_filter,
            intent=intent,
        )
        return StepResult(
            context_updates={
                "results": results,
                "timings": timings,
                "rerank_pool": rerank_pool,
                "variants_n": int(timings.get("query_variants_count", 1) or 1),
            }
        )


__all__ = ["EmbedSearchPass1Step"]
