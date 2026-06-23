"""Coverage metrics and gate step."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.helpers import finalize_reranked_hits, retrieval_bool_with_ui_override
from rag_service.config import get_retrieval_int
from rag_service.core.contracts import StepResult
from rag_service.domain.services.prompt_builder import framework_filter
from rag_service.domain.services.retrieval import compute_concept_coverage_report


class CoverageGateStep:
    id = "coverage_gate"
    icon = "rule"
    title = "Coverage gate"
    description = "Compute concept coverage and widen context window from rerank pool when needed."
    depends_on = ("rerank",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        timings = dict(ctx.get("timings") or {})
        results = framework_filter(question, list(ctx.get("results") or []))
        pool = framework_filter(question, list(ctx.get("rerank_pool") or []))
        fk = int(timings.get("final_context_k_used", 0) or 0)
        report = compute_concept_coverage_report(question, results)
        gate_applied = False
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

        return StepResult(
            context_updates={
                "results": results,
                "rerank_pool": pool,
                "timings": timings,
                "coverage_report": report,
                "coverage_gate_applied_flag": gate_applied,
            }
        )


__all__ = ["CoverageGateStep"]
