"""
Build a structured RAG pipeline trace for API/UI from timing counters (seconds).

Each step: id, label, status, duration_ms, optional detail.
"""

from __future__ import annotations

from typing import Any


def _ms(seconds: float) -> int:
    return int(round(max(0.0, float(seconds)) * 1000.0))


def build_rag_trace_from_timings(
    timings: dict[str, Any] | None,
    *,
    chunks_count: int,
    variants_count: int,
    retrieval_skipped: bool = False,
    context_assembly_extra: str | None = None,
) -> list[dict[str, Any]]:
    """
    Ordered steps for Material-dashboard-style timeline UI.

    ``timings`` uses seconds (same keys as ``search_rag`` / ``build_rag_context``).
    """
    t = timings or {}
    steps: list[dict[str, Any]] = []

    if retrieval_skipped:
        steps.append(
            {
                "id": "rag_skipped",
                "label": "RAG retrieval",
                "status": "skipped",
                "duration_ms": None,
                "detail": "Greeting or below trigger threshold",
            }
        )
        return steps

    steps.append(
        {
            "id": "query_prep",
            "label": "Query prep",
            "status": "ok",
            "duration_ms": _ms(float(t.get("expand_variants_s", 0.0) or 0.0)),
            "detail": f"{max(1, int(variants_count))} variant(s)" if variants_count else "1 variant",
        }
    )

    e1 = float(t.get("embed_s", 0.0) or 0.0)
    s1 = float(t.get("search_s", 0.0) or 0.0)
    steps.append(
        {
            "id": "embed_search_pass1",
            "label": "Embed + vector search (pass 1)",
            "status": "ok",
            "duration_ms": _ms(e1 + s1),
            "detail": None,
        }
    )

    p2e = float(t.get("pass2_embed_s", 0.0) or 0.0)
    p2s = float(t.get("pass2_search_s", 0.0) or 0.0)
    ran_p2 = (p2e + p2s) > 1e-9 or bool(int(t.get("concept_expansion_pass2_ran", 0) or 0))
    new_hits = int(t.get("concept_expansion_pass2_new_hits", 0) or 0)
    if ran_p2:
        steps.append(
            {
                "id": "concept_expansion_pass2",
                "label": "Concept expansion + pass 2",
                "status": "ok",
                "duration_ms": _ms(p2e + p2s),
                "detail": f"+{new_hits} new hit(s)" if new_hits else None,
            }
        )
    else:
        steps.append(
            {
                "id": "concept_expansion_pass2",
                "label": "Concept expansion + pass 2",
                "status": "skipped",
                "duration_ms": None,
                "detail": "Disabled or no mapped terms",
            }
        )

    n_cand = int(t.get("retrieval_candidates_n", 0) or 0)
    steps.append(
        {
            "id": "metadata_rank",
            "label": "Metadata rank",
            "status": "ok",
            "duration_ms": 0,
            "detail": f"{n_cand} candidate(s)" if n_cand else None,
        }
    )

    steps.append(
        {
            "id": "rerank",
            "label": "Rerank",
            "status": "ok",
            "duration_ms": _ms(float(t.get("rerank_s", 0.0) or 0.0)),
            "detail": None,
        }
    )

    cas = float(t.get("context_assembly_s", 0.0) or 0.0)
    ca_detail = f"{chunks_count} chunk(s) in prompt" if chunks_count else "No chunks"
    extra = (context_assembly_extra or "").strip()
    if extra:
        ca_detail = f"{ca_detail}; {extra}" if ca_detail else extra
    steps.append(
        {
            "id": "context_assembly",
            "label": "Context assembly",
            "status": "ok",
            "duration_ms": _ms(cas),
            "detail": ca_detail,
        }
    )

    return steps


__all__ = ["build_rag_trace_from_timings"]
