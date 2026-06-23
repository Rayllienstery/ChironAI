"""Final context assembly step for modular RAG core pipeline."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, MutableMapping

from rag_service.application.pipeline_steps.helpers import (
    build_rag_quality_from_report,
    coverage_trace_extra,
)
from rag_service.core.contracts import StepResult
from rag_service.domain.entities import RagContext
from rag_service.domain.services.prompt_builder import build_context_block
from rag_service.domain.services.rag_trace import build_rag_trace_from_timings

_rag_log = logging.getLogger("trag.rag")


class ContextAssemblyStep:
    """Build final context text and RagContext from retrieved hits."""

    id = "context_assembly"
    icon = "description"
    title = "Context assembly"
    description = "Build final context block and emit RagContext + trace."
    depends_on = ("coverage_supplemental",)

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return True

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx["question"])
        context_chunk_chars = int(ctx["context_chunk_chars"])
        context_total_chars = int(ctx["context_total_chars"])
        timings = dict(ctx.get("timings") or {})
        results = list(ctx.get("results") or [])
        variants_n = int(ctx.get("variants_n") or 1)
        report = dict(ctx.get("coverage_report") or {})
        gate_applied = bool(ctx.get("coverage_gate_applied_flag"))
        retry_search = bool(ctx.get("coverage_retry_search_flag"))

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

        timings["total_rag_s"] = (
            timings.get("embed_s", 0.0)
            + timings.get("search_s", 0.0)
            + timings.get("pass2_embed_s", 0.0)
            + timings.get("pass2_search_s", 0.0)
            + timings.get("rerank_s", 0.0)
            + timings.get("expand_variants_s", 0.0)
            + timings.get("concept_expansion_prep_s", 0.0)
        )
        rag_quality = build_rag_quality_from_report(report or {})
        structured = bool(ctx.get("structured_rag_context_enabled", False))
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
        trace_extra = coverage_trace_extra(report or {}, gate=gate_applied, retry_search=retry_search)
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
