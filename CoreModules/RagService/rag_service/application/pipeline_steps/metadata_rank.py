"""Metadata-aware ranking step."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.retrieval_flow import apply_metadata_rank
from rag_service.core.contracts import StepResult


class MetadataRankStep:
    id = "metadata_rank"
    icon = "sort"
    title = "Metadata rank"
    description = "Prioritize candidates by doc metadata and intent alignment."
    depends_on = ("concept_expansion_pass2",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        intent = ctx.get("intent")
        candidate_results = list(ctx.get("candidate_results") or [])
        ranked = apply_metadata_rank(candidate_results, intent)
        return StepResult(context_updates={"candidate_results": ranked})


__all__ = ["MetadataRankStep"]
