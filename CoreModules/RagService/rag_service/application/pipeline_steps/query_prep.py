"""Query preparation step for modular RAG core pipeline."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from rag_service.config import get_retrieval_int
from rag_service.core.contracts import StepResult
from rag_service.domain.services.retrieval import (
    MULTI_CHUNK_TOP_K,
    extra_filter_framework_equals,
    extra_filter_symbol_equals,
    infer_query_intent,
    merge_qdrant_filters,
    need_more_chunks,
)


class QueryPrepStep:
    """Prepare query-level retrieval parameters and intent-driven filters."""

    id = "query_prep"
    icon = "tune"
    title = "Query preparation"
    description = "Infer intent and build effective retrieval filters/limits."
    depends_on: tuple[str, ...] = ()

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        assert config is not None
        return bool((ctx.get("question") or "").strip())

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        question = str(ctx.get("question") or "")
        extra_filter = ctx.get("extra_filter")
        top_k = ctx.get("top_k")
        intent = infer_query_intent(question)
        intent_filter = merge_qdrant_filters(
            extra_filter_symbol_equals(intent.symbol),
            extra_filter_framework_equals(intent.framework),
        )
        combined_extra_filter = merge_qdrant_filters(extra_filter, intent_filter)
        if top_k is None:
            resolved_top_k = (
                MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", 8)
            )
        else:
            resolved_top_k = int(top_k)
        return StepResult(
            context_updates={
                "intent": intent,
                "combined_extra_filter": combined_extra_filter,
                "resolved_top_k": resolved_top_k,
            }
        )


__all__ = ["QueryPrepStep"]
