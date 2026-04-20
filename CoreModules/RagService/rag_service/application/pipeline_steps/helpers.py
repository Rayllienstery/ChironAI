"""Internal helper functions for modular RAG pipeline steps."""

from __future__ import annotations

from typing import Any

from rag_service.config import get_retrieval_bool
from rag_service.domain.services.retrieval import extract_target_concepts_for_coverage, select_hits_for_concept_coverage


def retrieval_bool_with_ui_override(key: str, *, yaml_fallback: bool = False) -> bool:
    return get_retrieval_bool(key, yaml_fallback)


def finalize_reranked_hits(
    question: str,
    hits: list[dict[str, Any]],
    final_k: int,
) -> list[dict[str, Any]]:
    """Take first final_k after rerank, or coverage-aware subset when enabled and concepts exist."""
    if not hits:
        return []
    if not retrieval_bool_with_ui_override("coverage_aware_selection"):
        return hits[:final_k]
    concepts = extract_target_concepts_for_coverage(question)
    if not concepts:
        return hits[:final_k]
    return select_hits_for_concept_coverage(hits, concepts, final_k)


def build_rag_quality_from_report(report: dict[str, Any]) -> dict[str, Any] | None:
    targets = report.get("target_concepts") or []
    if not targets:
        return None
    missing = report.get("missing_concepts") or []
    if missing:
        return {
            "failure_class": "retrieval_gap",
            "missing_concepts": missing[:24],
            "coverage_ratio": report.get("coverage_ratio"),
        }
    return {"failure_class": "ok", "coverage_ratio": report.get("coverage_ratio")}


def coverage_trace_extra(
    report: dict[str, Any],
    *,
    gate: bool,
    retry_search: bool,
) -> str | None:
    parts: list[str] = []
    r = report.get("coverage_ratio")
    if r is not None:
        parts.append(f"coverage={r:.2f}")
    m = report.get("missing_concepts") or []
    if m:
        parts.append(f"missing={len(m)}")
    if gate:
        parts.append("gate_widen")
    if retry_search:
        parts.append("retry_search")
    return "; ".join(parts) if parts else None


__all__ = ["build_rag_quality_from_report", "coverage_trace_extra", "finalize_reranked_hits"]
