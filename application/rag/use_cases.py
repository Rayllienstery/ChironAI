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

from domain.entities.rag import RagAnswerResponse, RagContext, RagQuestionRequest
from domain.ports import ChatLLMClient, EmbeddingProvider, RagRepository, RerankClient
from domain.services.prompt_builder import (
    build_context_block,
    build_system_content,
    framework_filter,
    last_user_content,
)
from domain.services.rerank import (
    apply_rerank_scores_and_cut,
    build_rerank_prompt,
    parse_rerank_order,
    reorder_hits_by_indices,
)
from domain.services.rag_trigger import compute_rag_trigger_score
from infrastructure.ollama.openai_ollama_tool_bridge import openai_messages_to_ollama
from domain.services.retrieval import (
    FINAL_CONTEXT_K,
    MULTI_CHUNK_FINAL_K,
    MULTI_CHUNK_TOP_K,
    RERANK_MAX_CANDIDATES,
    build_qdrant_filter,
    merge_qdrant_filters,
    combined_doc_priority,
    doc_type_priority,
    expand_query_variants,
    is_version_question,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
    rrf_merge_hit_lists,
    should_skip_rag_search,
)
from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector

_rag_log = logging.getLogger("trag.rag")

try:
    from config import get_retrieval_int
except ImportError:
    get_retrieval_int = lambda k, d: d  # type: ignore
DEFAULT_TOP_K = 8


def _apply_rerank(
    question: str,
    hits: list[dict[str, Any]],
    rerank_client: RerankClient | None,
    final_k: int,
    timings: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Apply LLM rerank and cut to final_k. Uses domain rerank logic + rerank_client."""
    if not hits:
        return []
    candidates = hits[:RERANK_MAX_CANDIDATES]
    candidate_texts = [
        (idx, (h.get("payload") or {}).get("text", ""))
        for idx, h in enumerate(candidates, start=1)
    ]
    prompt_text = build_rerank_prompt(question, candidate_texts)
    if timings is not None:
        timings["rerank_prompt_tokens_in"] = timings.get("rerank_prompt_tokens_in", 0.0) + (
            0 if not prompt_text else max(1, int(len(prompt_text) / 4))
        )
    raw = rerank_client.rerank(question, prompt_text) if rerank_client else None
    order = parse_rerank_order(raw) if raw else None
    if order is not None:
        hits = reorder_hits_by_indices(candidates, order, hits)
    else:
        hits = list(hits)
    return apply_rerank_scores_and_cut(hits, final_k)


def _search_one(
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    search_query: str,
    top_k: int,
    filter_dict: dict[str, Any] | None,
    *,
    hybrid_on: bool,
    timings: dict[str, float],
) -> list[dict[str, Any]]:
    t0 = time.perf_counter()
    vec = embed_provider.embed(search_query)
    timings["embed_s"] += time.perf_counter() - t0
    timings["embed_tokens_in"] += 0 if not search_query else max(1, int(len(search_query) / 4))
    si: list[int] | None = None
    sv: list[float] | None = None
    if hybrid_on:
        si, sv = text_to_sparse_vector(normalize_text_for_sparse(search_query))
        if not si:
            si, sv = None, None
    t0 = time.perf_counter()
    if si and sv:
        results = rag_repo.search(
            vec,
            top_k=top_k,
            filter_dict=filter_dict,
            sparse_indices=si,
            sparse_values=sv,
        )
    else:
        results = rag_repo.search(vec, top_k=top_k, filter_dict=filter_dict)
    if filter_dict and not results:
        if si and sv:
            results = rag_repo.search(
                vec,
                top_k=top_k,
                filter_dict=None,
                sparse_indices=si,
                sparse_values=sv,
            )
        else:
            results = rag_repo.search(vec, top_k=top_k, filter_dict=None)
    timings["search_s"] += time.perf_counter() - t0
    return results


def search_rag(
    question: str,
    rag_repo: RagRepository,
    embed_provider: EmbeddingProvider,
    rerank_client: RerankClient | None,
    top_k: int | None = None,
    extra_filter: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """
    Run RAG retrieval for a question: query_for_retrieval -> embed -> search -> rerank.
    Returns (list of hits with id, score, payload, rerank_score, timings dict with embed_s, search_s, rerank_s).

    ``extra_filter`` is merged with ``build_qdrant_filter(question)`` via ``merge_qdrant_filters``
    (e.g. ``extra_filter_section_path_joined_equals`` for section-scoped search).
    """
    timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "expand_variants_s": 0.0,
        # Token estimates for UI trace; true tokenization isn't available here.
        "embed_tokens_in": 0.0,
        "rerank_prompt_tokens_in": 0.0,
    }
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else get_retrieval_int("top_k", DEFAULT_TOP_K)
    hybrid_on = is_hybrid_sparse_enabled() and rag_repo.supports_hybrid()
    filter_dict = merge_qdrant_filters(build_qdrant_filter(question), extra_filter)
    k = max(top_k, RERANK_MAX_CANDIDATES) if not is_version_question(question) else top_k
    final_k = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K

    if not is_version_question(question):
        t_exp0 = time.perf_counter()
        variants = expand_query_variants(question)
        timings["expand_variants_s"] += time.perf_counter() - t_exp0
        per_variant_k = max(4, min(k, max(4, k // max(1, len(variants)))))
        lists: list[list[dict[str, Any]]] = []
        for variant in variants:
            sq = query_for_retrieval(variant)
            lists.append(
                _search_one(
                    rag_repo,
                    embed_provider,
                    sq,
                    per_variant_k,
                    filter_dict,
                    hybrid_on=hybrid_on,
                    timings=timings,
                )
            )
        if len(lists) == 1:
            results = lists[0]
        else:
            results = rrf_merge_hit_lists(lists, limit=k)
        results.sort(key=combined_doc_priority, reverse=True)
        t0 = time.perf_counter()
        results = _apply_rerank(question, results, rerank_client, final_k, timings=timings)
        timings["rerank_s"] += time.perf_counter() - t0
        return results, timings
    search_query = query_for_retrieval(question)
    results = _search_one(
        rag_repo,
        embed_provider,
        search_query,
        k,
        filter_dict,
        hybrid_on=hybrid_on,
        timings=timings,
    )
    ios_q, swift_q = parse_versions_from_question(question)
    extra_results: list[dict[str, Any]] = []
    for v in swift_q:
        qv = f"Swift {v} version RELEASE"
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                qv,
                6,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                qv,
                6,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    if not extra_results:
        extra_results.extend(
            _search_one(
                rag_repo,
                embed_provider,
                "Swift version release number RELEASE",
                8,
                filter_dict,
                hybrid_on=hybrid_on,
                timings=timings,
            )
        )
    seen_ids = {r["id"] for r in results}
    for r in extra_results:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])
    ios_set = set(ios_q)
    swift_set = set(swift_q)

    def _score(h: dict[str, Any]) -> int:
        payload = h.get("payload") or {}
        ios_payload = set(payload.get("ios_versions") or [])
        swift_payload = set(payload.get("swift_versions") or [])
        s = 0
        if ios_set and ios_payload & ios_set:
            s += 3
        if swift_set and swift_payload & swift_set:
            s += 3
        if (ios_set or swift_set) and (ios_payload or swift_payload):
            s += 1
        return s

    if ios_set or swift_set:
        results.sort(key=_score, reverse=True)
        results.sort(key=combined_doc_priority, reverse=True)
    t0 = time.perf_counter()
    results = _apply_rerank(question, results, rerank_client, final_k, timings=timings)
    timings["rerank_s"] += time.perf_counter() - t0
    return results, timings


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
        "total_rag_s": 0.0,
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
        return RagContext("", [], 0.0), empty_timings
    try:
        results, timings = search_rag(
            question,
            rag_repo,
            embed_provider,
            rerank_client,
            top_k=top_k,
            extra_filter=extra_filter,
        )
        timings["total_rag_s"] = (
            timings["embed_s"]
            + timings["search_s"]
            + timings["rerank_s"]
            + timings.get("expand_variants_s", 0.0)
        )
        if not results:
            return RagContext("", [], 0.0), timings
        results = framework_filter(question, results)
        context_text, chunks_info, max_score = build_context_block(
            results, context_chunk_chars, context_total_chars
        )
        count = len(chunks_info)
        if count:
            sources = list({c.get("doc_type") or "N/A" for c in chunks_info})
            _rag_log.info(
                "RAG chunks count=%s max_score=%.2f sources=%s embed_s=%.2f search_s=%.2f rerank_s=%.2f total_rag_s=%.2f",
                count,
                max_score,
                ",".join(str(s) for s in sources[:5]),
                timings["embed_s"],
                timings["search_s"],
                timings["rerank_s"],
                timings["total_rag_s"],
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
        return RagContext(context_text=context_text, chunks_info=chunks_info, max_score=max_score), timings
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
    system_content = build_system_content(
        system_prefix,
        system_suffix,
        ctx.context_text,
        ctx.max_score,
        confidence_threshold,
        reasoning_level,
        model_name,
        retrieval_skipped=ctx.retrieval_skipped,
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
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
            else:
                text = content or ""
            ollama_messages.append({"role": role, "content": text})
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
                text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
            else:
                text = content or ""
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
            ollama_messages.append({"role": role, "content": text})
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
