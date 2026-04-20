"""
RAG application use cases.

Orchestrates retrieval (embed, search, rerank) and chat using domain services
and injected ports (RagRepository, EmbeddingProvider, RerankClient, ChatLLMClient).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from rag_service.application.pipeline_steps.context_assembly import ContextAssemblyStep
from rag_service.application.pipeline_steps.concept_expansion_pass2 import ConceptExpansionPass2Step
from rag_service.application.pipeline_steps.coverage_gate import CoverageGateStep
from rag_service.application.pipeline_steps.coverage_supplemental import CoverageSupplementalStep
from rag_service.application.pipeline_steps.embed_search_pass1 import EmbedSearchPass1Step
from rag_service.application.pipeline_steps.helpers import finalize_reranked_hits
from rag_service.application.pipeline_steps.metadata_rank import MetadataRankStep
from rag_service.application.pipeline_steps.query_prep import QueryPrepStep
from rag_service.application.pipeline_steps.rerank import RerankStep
from rag_service.application.pipeline_steps.retrieval_flow import (
    apply_metadata_rank,
    apply_rerank as _rf_apply_rerank,
    init_retrieval_timings,
    retrieve_pass1_candidates,
    search_one as _rf_search_one,
    maybe_apply_concept_expansion,
)
from rag_service.config import get_retrieval_bool, get_retrieval_int
from rag_service.core import RagCore, StepRegistry
from rag_service.domain.entities import QueryIntent, RagAnswerResponse, RagContext, RagQuestionRequest
from rag_service.domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from rag_service.domain.services.prompt_builder import (
    build_system_content,
    last_user_content,
)
from rag_service.domain.services.rag_trace import build_rag_trace_from_timings
from rag_service.domain.services.rag_trigger import compute_rag_trigger_score
from rag_service.domain.services.retrieval import (
    MULTI_CHUNK_TOP_K,
    compute_concept_coverage_report,
    need_more_chunks,
    should_skip_rag_search,
)
from rag_service.infrastructure.openai_multipart_vision import (
    collect_ollama_images_b64_from_parts,
    openai_parts_to_flat_text,
)
from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama

_rag_log = logging.getLogger("trag.rag")

DEFAULT_TOP_K = 8


def retrieval_bool_with_ui_override(key: str, *, yaml_fallback: bool = False) -> bool:
    return get_retrieval_bool(key, yaml_fallback)


def is_hybrid_sparse_enabled() -> bool:
    return get_retrieval_bool("hybrid_sparse_enabled", True)


def _apply_rerank(
    question: str,
    hits: list[dict[str, Any]],
    rerank_client: RerankClient | None,
    timings: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    return _rf_apply_rerank(question, hits, rerank_client, timings)


def _finalize_reranked_hits(
    question: str,
    hits: list[dict[str, Any]],
    final_k: int,
) -> list[dict[str, Any]]:
    return finalize_reranked_hits(question, hits, final_k)


def _search_one(
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    search_query: str,
    top_k: int,
    filter_dict: dict[str, Any] | None,
    *,
    hybrid_on: bool,
    timings: dict[str, float],
    embed_key: str = "embed_s",
    search_key: str = "search_s",
) -> list[dict[str, Any]]:
    return _rf_search_one(
        rag_repo,
        embed_provider,
        search_query,
        top_k,
        filter_dict,
        hybrid_on=hybrid_on,
        timings=timings,
        embed_key=embed_key,
        search_key=search_key,
    )


def search_rag(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    top_k: int | None = None,
    extra_filter: dict[str, Any] | None = None,
    intent: QueryIntent | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float], list[dict[str, Any]]]:
    """
    Run RAG retrieval for a question: query_for_retrieval -> embed -> search -> rerank.
    Returns (final hits, timings, rerank_pool) where ``rerank_pool`` is the full reranked list
    before cutting to ``final_k`` (for coverage gate / widen without re-embedding).

    ``extra_filter`` is merged with ``build_qdrant_filter(question)`` via ``merge_qdrant_filters``
    (e.g. ``extra_filter_section_path_joined_equals`` for section-scoped search).
    """
    timings = init_retrieval_timings()
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", DEFAULT_TOP_K)
    results, final_k = retrieve_pass1_candidates(
        question,
        rag_repo,
        embed_provider,
        top_k=top_k,
        extra_filter=extra_filter,
        timings=timings,
    )
    results = maybe_apply_concept_expansion(
        question,
        results,
        rag_repo,
        embed_provider,
        extra_filter=extra_filter,
        timings=timings,
    )
    results = apply_metadata_rank(results, intent)
    timings["retrieval_candidates_n"] = float(len(results))
    t0 = time.perf_counter()
    results = _apply_rerank(question, results, rerank_client, timings=timings)
    rerank_pool = list(results)
    results = _finalize_reranked_hits(question, rerank_pool, final_k)
    timings["final_context_k_used"] = float(final_k)
    timings["rerank_s"] += time.perf_counter() - t0
    return results, timings, rerank_pool


def _build_rag_quality_from_report(report: dict[str, Any]) -> dict[str, Any] | None:
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


def _coverage_trace_extra(
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


def _build_base_rag_core() -> RagCore:
    registry = StepRegistry()
    registry.register(QueryPrepStep())
    registry.register(EmbedSearchPass1Step())
    registry.register(ConceptExpansionPass2Step())
    registry.register(MetadataRankStep())
    registry.register(RerankStep())
    registry.register(CoverageGateStep())
    registry.register(CoverageSupplementalStep())
    registry.register(ContextAssemblyStep())
    return RagCore(registry)


def build_rag_context(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    context_chunk_chars: int,
    context_total_chars: int,
    top_k: int | None = None,
    rag_required_keywords: list[str] | None = None,
    trigger_threshold: int | None = None,
    force_rag: bool = False,
    extra_filter: dict[str, Any] | None = None,
) -> tuple[RagContext, dict[str, float]]:
    """
    Build RAG context for a question: search_rag -> framework_filter -> build_context_block.
    Returns (RagContext (context_text, chunks_info, max_score), timings dict with embed_s, search_s, rerank_s, total_rag_s).
    If rag_required_keywords is provided, it is used to decide when to skip RAG (no keyword in query); else config default.
    trigger_threshold overrides config when provided (e.g. from app settings).
    ``extra_filter`` is passed to ``search_rag`` (merged with doc_type/doc_scope preference filter).
    """
    empty_timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "expand_variants_s": 0.0,
        "pass2_embed_s": 0.0,
        "pass2_search_s": 0.0,
        "concept_expansion_prep_s": 0.0,
        "concept_expansion_pass2_ran": 0.0,
        "concept_expansion_pass2_new_hits": 0.0,
        "retrieval_candidates_n": 0.0,
        "query_variants_count": 1.0,
        "context_assembly_s": 0.0,
        "total_rag_s": 0.0,
        "final_context_k_used": 0.0,
        "coverage_gate_applied": 0.0,
        "coverage_retry_search_s": 0.0,
    }
    if not question or not question.strip():
        return RagContext("", [], 0.0), empty_timings
    score, signals, triggered = compute_rag_trigger_score(
        question, rag_required_keywords=rag_required_keywords, trigger_threshold=trigger_threshold
    )
    _rag_log.debug("RAG trigger score=%s signals=%s triggered=%s force_rag=%s", score, signals, triggered, force_rag)
    if not force_rag and should_skip_rag_search(
        question, rag_required_keywords=rag_required_keywords, trigger_threshold=trigger_threshold
    ):
        _rag_log.debug("RAG skipped for query (greeting or score below threshold)")
        _rt_skip = build_rag_trace_from_timings(
            empty_timings, chunks_count=0, variants_count=0, retrieval_skipped=True
        )
        return RagContext("", [], 0.0, rag_trace=_rt_skip), empty_timings
    try:
        core = _build_base_rag_core()
        run_out = core.run_pipeline(
            request={"question": question},
            initial_context={
                "question": question,
                "extra_filter": extra_filter,
                "top_k": top_k,
                "rag_repo": rag_repo,
                "embed_provider": embed_provider,
                "rerank_client": rerank_client,
                "context_chunk_chars": context_chunk_chars,
                "context_total_chars": context_total_chars,
            },
        )
        rag_ctx = run_out.context.get("rag_context")
        timings = run_out.context.get("timings")
        if isinstance(rag_ctx, RagContext) and isinstance(timings, dict):
            return rag_ctx, timings
        _rag_log.warning("RagCore base pipeline returned incomplete payload; falling back to empty context")
        return RagContext("", [], 0.0), empty_timings
    except Exception as e:
        _rag_log.exception("RAG build_rag_context failed: %s", e)
        return RagContext("", [], 0.0), empty_timings


def answer_question(
    request: RagQuestionRequest,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    chat_client: ChatLLMClient,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: str | None = None,
    rag_required_keywords: list[str] | None = None,
    rag_context: RagContext | None = None,
    trigger_threshold: int | None = None,
    force_rag: bool = False,
    extra_filter: dict[str, Any] | None = None,
) -> RagAnswerResponse:
    """
    Answer a question with RAG: build_rag_context (or use rag_context) -> build_system_content -> chat.
    Returns RagAnswerResponse (content, model, finish_reason).
    When rag_context is provided, RAG retrieval is skipped and the given context is used.
    """
    last_user = last_user_content(request.messages)
    if rag_context is not None:
        ctx = rag_context
    else:
        ctx, _ = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            rerank_client,
            context_chunk_chars,
            context_total_chars,
            rag_required_keywords=rag_required_keywords,
            trigger_threshold=trigger_threshold,
            force_rag=force_rag,
            extra_filter=extra_filter,
        )
    _miss = (ctx.coverage_report or {}).get("missing_concepts") if ctx.coverage_report else None
    _miss_list = _miss if isinstance(_miss, list) else None
    system_content = build_system_content(
        system_prefix,
        system_suffix,
        ctx.context_text,
        ctx.max_score,
        confidence_threshold,
        reasoning_level,
        model_name,
        retrieval_skipped=ctx.retrieval_skipped,
        coverage_missing_concepts=_miss_list,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            if isinstance(content, list):
                text = openai_parts_to_flat_text(content)
                images = collect_ollama_images_b64_from_parts(content) if role == "user" else []
            else:
                text = content or ""
                images = []
            msg: dict[str, Any] = {"role": role, "content": text}
            if role == "user" and images:
                msg["images"] = images
            ollama_messages.append(msg)
    model = request.model or model_name
    content = chat_client.chat(ollama_messages, model, stream=False, options=None)
    return RagAnswerResponse(content=content, model=model, finish_reason="stop")


def prepare_ollama_messages(
    request: RagQuestionRequest,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    system_prefix: str,
    system_suffix: str,
    context_chunk_chars: int,
    context_total_chars: int,
    confidence_threshold: float,
    model_name: str,
    reasoning_level: str | None = None,
    rag_required_keywords: list[str] | None = None,
    rag_context: RagContext | None = None,
    trigger_threshold: int | None = None,
    force_rag: bool = False,
    extra_filter: dict[str, Any] | None = None,
    *,
    native_tools: bool = False,
    web_supplement: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Build RAG context (unless rag_context provided) and Ollama message list (for streaming or custom chat).
    Returns (ollama_messages, model).
    When rag_context is provided, RAG retrieval is skipped and the given context is used.
    When native_tools is True, preserve OpenAI tool protocol (assistant tool_calls, tool role) for Ollama /api/chat.
    Optional web_supplement is inserted after the RAG context in the system message (e.g. DuckDuckGo snippets).
    """
    last_user = last_user_content(request.messages)
    if rag_context is not None:
        ctx = rag_context
    else:
        ctx, _ = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            rerank_client,
            context_chunk_chars,
            context_total_chars,
            rag_required_keywords=rag_required_keywords,
            trigger_threshold=trigger_threshold,
            force_rag=force_rag,
            extra_filter=extra_filter,
        )
    _miss2 = (ctx.coverage_report or {}).get("missing_concepts") if ctx.coverage_report else None
    _miss_list2 = _miss2 if isinstance(_miss2, list) else None
    system_content = build_system_content(
        system_prefix,
        system_suffix,
        ctx.context_text,
        ctx.max_score,
        confidence_threshold,
        reasoning_level,
        model_name,
        web_supplement=web_supplement,
        retrieval_skipped=ctx.retrieval_skipped,
        coverage_missing_concepts=_miss_list2,
    )
    ollama_messages = [{"role": "system", "content": system_content}]
    if native_tools:
        raw_msgs = [m for m in request.messages if isinstance(m, dict)]
        ollama_messages.extend(openai_messages_to_ollama(raw_msgs))
        model = request.model or model_name
        return ollama_messages, model

    # ZED/OpenAI tool-result messages may omit `name` and provide `tool_call_id` instead.
    # Build a lookup from tool_call_id -> tool function name so we can label tool results
    # consistently in our plain-text Ollama prompt.
    tool_call_id_to_name: dict[str, str] = {}
    for m in request.messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for c in tool_calls:
            if not isinstance(c, dict):
                continue
            call_id = c.get("id")
            fn = c.get("function")
            name = fn.get("name") if isinstance(fn, dict) else None
            if isinstance(call_id, str) and call_id and isinstance(name, str) and name:
                tool_call_id_to_name[call_id] = name
    for m in request.messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            ollama_messages.append({"role": "system", "content": (content or "")})
            continue
        if role in ("user", "assistant"):
            if isinstance(content, list):
                text = openai_parts_to_flat_text(content)
                images = collect_ollama_images_b64_from_parts(content) if role == "user" else []
            else:
                text = content or ""
                images = []
            # Preserve assistant tool-call turn in text form for models without native tool role.
            if role == "assistant" and not text and isinstance(m.get("tool_calls"), list):
                tc = m.get("tool_calls") or []
                parts: list[str] = []
                for c in tc:
                    if not isinstance(c, dict):
                        continue
                    fn = (c.get("function") or {}) if isinstance(c.get("function"), dict) else {}
                    name = fn.get("name") or "tool"
                    args = fn.get("arguments") or ""
                    parts.append(f"[tool_call:{name}] {args}")
                text = "\n".join(parts)
            msg2: dict[str, Any] = {"role": role, "content": text}
            if role == "user" and images:
                msg2["images"] = images
            ollama_messages.append(msg2)
            continue
        if role == "tool":
            # Prefer explicit `name`, otherwise infer from `tool_call_id`.
            name = m.get("name")
            if not isinstance(name, str) or not name:
                tool_call_id = m.get("tool_call_id") or m.get("tool_callid")
                if isinstance(tool_call_id, str) and tool_call_id:
                    name = tool_call_id_to_name.get(tool_call_id)
            if not isinstance(name, str) or not name:
                name = "tool"
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            ollama_messages.append({"role": "user", "content": f"[tool_result:{name}] {text}"})
    model = request.model or model_name
    return ollama_messages, model


__all__ = [
    "answer_question",
    "build_rag_context",
    "prepare_ollama_messages",
    "search_rag",
]
