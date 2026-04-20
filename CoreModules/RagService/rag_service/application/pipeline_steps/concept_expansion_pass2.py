"""Optional concept expansion pass-2 retrieval step."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.retrieval_flow import maybe_apply_concept_expansion
from rag_service.core.contracts import StepResult


class ConceptExpansionPass2Step:
    id = "concept_expansion_pass2"
    icon = "hub"
    title = "Concept expansion pass 2"
    description = "Expand concepts and retrieve supplemental pass-2 candidates when enabled."
    depends_on = ("embed_search_pass1",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        rag_repo = ctx["rag_repo"]
        embed_provider = ctx["embed_provider"]
        combined_extra_filter = ctx.get("combined_extra_filter")
        timings = dict(ctx.get("timings") or {})
        candidate_results = list(ctx.get("candidate_results") or [])
        expanded = maybe_apply_concept_expansion(
            question,
            candidate_results,
            rag_repo,
            embed_provider,
            extra_filter=combined_extra_filter,
            timings=timings,
        )
        timings["retrieval_candidates_n"] = float(len(expanded))
        return StepResult(context_updates={"candidate_results": expanded, "timings": timings})


__all__ = ["ConceptExpansionPass2Step"]
