"""RAG retrieval and web-supplement orchestration for chat completions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from llm_proxy.chat_completions_handler_helpers import (
    append_pipeline_step_trace,
)
from llm_proxy.chat_completions_rag_prep import (
    build_framework_name_to_collection_map,
    build_rag_context_log_snapshot,
    enrich_rag_trace_for_ui,
    resolve_project_fresh_collections,
)
from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.pipeline_steps.merged_docs_step import run_merged_docs_step
from llm_proxy.pipeline_steps.web_supplement_step import run_web_supplement_step
from llm_proxy.tool_helpers import (
    _extract_file_path_from_user_text,
    _extract_line_span_from_user_text,
    _workspace_doc_refactor_intent,
)

_RAG_LOG = logging.getLogger("llm_proxy")

PublishTraceFn = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ProjectContextResolution:
    project_fresh_collection_names: set[str] | None
    needs_refresh: list[tuple[str, str]]


def resolve_project_context_collections(
    *,
    w: LlmProxyWiring,
    fetch_web_knowledge: bool,
    project_context: Any,
) -> ProjectContextResolution:
    """Resolve fresh framework-linked collections when project_context is present."""
    if not (
        fetch_web_knowledge
        and isinstance(project_context, dict)
        and w.external_docs.available
        and w.external_docs.load_rag_sources_config
    ):
        return ProjectContextResolution(project_fresh_collection_names=None, needs_refresh=[])

    frameworks = project_context.get("frameworks") or []
    if not frameworks:
        return ProjectContextResolution(project_fresh_collection_names=None, needs_refresh=[])

    rag_sources_config = w.external_docs.load_rag_sources_config()
    name_to_collection = build_framework_name_to_collection_map(rag_sources_config)
    prep_settings_repo = None
    try:
        prep_settings_repo = w.get_settings_repository()
    except Exception:
        pass
    fresh_names, needs_refresh = resolve_project_fresh_collections(
        frameworks,
        name_to_collection=name_to_collection,
        settings_repo=prep_settings_repo,
        check_collection_freshness=w.check_collection_freshness,
        default_ttl_days=w.get_framework_collection_ttl_days(),
    )
    return ProjectContextResolution(
        project_fresh_collection_names=fresh_names,
        needs_refresh=needs_refresh,
    )


@dataclass(frozen=True)
class SkipRagRetrievalResolution:
    skip_rag_retrieval: bool
    doc_refactor_intent: bool
    doc_refactor_skip: bool
    local_tool_edit_fast_path: bool


def resolve_skip_rag_retrieval(
    *,
    body: dict[str, Any],
    last_user: str,
    tools: list[Any],
    selected_edit_tool_name: str | None,
    tool_choice_effective: str,
    use_native_tools: bool,
    force_rag: bool,
    fetch_web_knowledge: bool,
    request_collection: str | None,
    post_tool_success_turn: bool,
    is_autocomplete: bool,
    dumb_build_pipeline: bool,
    proxy_settings: dict[str, Any],
) -> SkipRagRetrievalResolution:
    explicit_skip_rag = bool(body.get("skip_rag"))
    doc_refactor_intent = bool(_workspace_doc_refactor_intent(last_user or ""))
    doc_refactor_skip = bool(doc_refactor_intent and not force_rag)
    local_tool_edit_fast_path = (
        bool(tools)
        and bool(selected_edit_tool_name)
        and tool_choice_effective != "none"
        and not use_native_tools
        and not force_rag
        and not fetch_web_knowledge
        and not request_collection
        and (
            post_tool_success_turn
            or (
                bool(_extract_file_path_from_user_text(last_user or ""))
                and _extract_line_span_from_user_text(last_user or "") is not None
            )
        )
    )
    skip_rag_retrieval = (
        explicit_skip_rag
        or local_tool_edit_fast_path
        or is_autocomplete
        or doc_refactor_skip
        or (dumb_build_pipeline and not bool(proxy_settings.get("rag_enabled", True)))
    )
    return SkipRagRetrievalResolution(
        skip_rag_retrieval=skip_rag_retrieval,
        doc_refactor_intent=doc_refactor_intent,
        doc_refactor_skip=doc_refactor_skip,
        local_tool_edit_fast_path=local_tool_edit_fast_path,
    )


@dataclass(frozen=True)
class RagPipelineResult:
    rag_ctx_for_log: Any | None
    rag_timings: dict[str, float]
    rag_context_data: dict[str, Any] | None
    background_refresh_started: bool
    web_supplement_text: str | None
    web_sup_meta: dict[str, Any]


def run_chat_rag_pipeline(
    *,
    w: LlmProxyWiring,
    trace: dict[str, Any],
    last_user: str,
    messages: list[Any],
    body: dict[str, Any],
    fetch_web_knowledge: bool,
    request_collection: str | None,
    effective_rag_repo: Any,
    effective_embed_provider: Any,
    effective_rerank_client: Any,
    effective_context_chunk_chars: int,
    effective_context_total_chars: int,
    effective_confidence_threshold: float,
    effective_rag_top_k: int | None,
    rag_keywords: Any,
    force_rag: bool,
    skip_rag_retrieval: bool,
    is_autocomplete: bool,
    doc_refactor_skip: bool,
    proxy_settings: dict[str, Any],
    project_fresh_collection_names: set[str] | None,
    needs_refresh: list[tuple[str, str]],
    private_build: bool,
    publish_trace: PublishTraceFn,
) -> RagPipelineResult:
    """Run merged-docs RAG retrieval, trace enrichment, and web supplement."""
    rag_ctx_for_log = None
    rag_timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "total_rag_s": 0.0,
    }
    background_refresh_started = False
    trace["internet"] = {"background_refresh_started": False}
    rag_context_data: dict[str, Any] | None = None

    try:
        if skip_rag_retrieval:
            rag_ctx_for_log = w.rag_context_factory(
                context_text="", chunks_info=[], max_score=0.0, retrieval_skipped=True
            )
            trace["rag"]["retrieval_skipped"] = True
        else:
            trace["rag"]["retrieval_skipped"] = False

        merged_step_status = "disabled"
        merged_step_reason: str | None = None
        if not skip_rag_retrieval:
            merged_step = run_merged_docs_step(
                w=w,
                last_user=last_user,
                messages=messages,
                body=body,
                fetch_web_knowledge=bool(fetch_web_knowledge),
                request_collection=request_collection,
                effective_embed_provider=effective_embed_provider,
                effective_context_chunk_chars=effective_context_chunk_chars,
                effective_context_total_chars=effective_context_total_chars,
                project_fresh_collection_names=project_fresh_collection_names,
                needs_refresh=needs_refresh,
                logger=_RAG_LOG,
            )
            merged_step_status = merged_step.status
            merged_step_reason = merged_step.reason
            background_refresh_started = bool(merged_step.background_refresh_started)
            trace["internet"]["background_refresh_started"] = background_refresh_started
            if merged_step.used and merged_step.rag_ctx_for_log is not None:
                rag_ctx_for_log = merged_step.rag_ctx_for_log
                rag_timings = merged_step.rag_timings
            else:
                rag_ctx_for_log, rag_timings = w.build_rag_context(
                    last_user,
                    effective_rag_repo,
                    effective_embed_provider,
                    effective_rerank_client,
                    effective_context_chunk_chars,
                    effective_context_total_chars,
                    top_k=effective_rag_top_k,
                    rag_required_keywords=rag_keywords,
                    trigger_threshold=None,
                    force_rag=force_rag,
                )
        else:
            merged_step_status = "skipped"
            merged_step_reason = "rag_retrieval_skipped"
        append_pipeline_step_trace(
            trace,
            step_id="merged_docs",
            status=merged_step_status,
            reason=merged_step_reason,
        )
        if rag_timings:
            w.set_latest_request_rag_steps(rag_timings)
            if not private_build:
                _RAG_LOG.debug(
                    "RAG steps embed_s=%.2f search_s=%.2f rerank_s=%.2f fetch_s=%.2f discovery_s=%.2f total_rag_s=%.2f",
                    rag_timings.get("embed_s", 0),
                    rag_timings.get("search_s", 0),
                    rag_timings.get("rerank_s", 0),
                    rag_timings.get("fetch_s", 0),
                    rag_timings.get("discovery_s", 0),
                    rag_timings.get("total_rag_s", 0),
                )
        rag_context_data = build_rag_context_log_snapshot(rag_ctx_for_log)

        enrich_rag_trace_for_ui(
            trace,
            rag_ctx_for_log=rag_ctx_for_log,
            rag_timings=rag_timings,
            effective_context_total_chars=effective_context_total_chars,
            background_refresh_started=background_refresh_started,
        )
        publish_trace(trace)
    except Exception as exc:
        if not private_build:
            _RAG_LOG.warning("Failed to build RAG context for logging: %s", exc)
        rag_context_data = None

    w.set_proxy_status(w.status_preparing_response)

    web_supplement_text: str | None = None
    web_sup_meta: dict[str, Any] = {
        "trigger": "none",
        "used": False,
        "error": None,
        "duration_ms": 0,
        "snippets_chars": 0,
    }
    web_step = run_web_supplement_step(
        w=w,
        is_autocomplete=bool(is_autocomplete),
        doc_refactor_skip=bool(doc_refactor_skip),
        last_user=last_user or "",
        rag_ctx_for_log=rag_ctx_for_log,
        effective_confidence_threshold=float(effective_confidence_threshold),
        proxy_settings={str(k): v for k, v in (proxy_settings or {}).items()},
    )
    web_supplement_text = web_step.text
    web_sup_meta = dict(web_step.meta or {})
    trace["internet"]["web_supplement"] = {
        "used": bool(web_sup_meta.get("used")),
        "trigger": web_sup_meta.get("trigger"),
        "error": web_sup_meta.get("error"),
        "duration_ms": web_sup_meta.get("duration_ms", 0),
        "snippets_chars": web_sup_meta.get("snippets_chars", 0),
        "queries": web_sup_meta.get("queries") or [],
        "cache_hit": bool(web_sup_meta.get("cache_hit")),
        "fetch_used": bool(web_sup_meta.get("fetch_used")),
        "wikipedia_used": bool(web_sup_meta.get("wikipedia_used")),
        "ddg_news": bool(web_sup_meta.get("ddg_news")),
        "domains_top": web_sup_meta.get("domains_top") or [],
        "snippets_count": int(web_sup_meta.get("snippets_count") or 0),
    }
    trace["internet"]["used"] = bool(
        trace["internet"].get("used") or trace["internet"]["web_supplement"].get("used")
    )
    append_pipeline_step_trace(
        trace,
        step_id="web_supplement",
        status=web_step.status,
        reason=web_step.reason,
    )
    publish_trace(trace)

    return RagPipelineResult(
        rag_ctx_for_log=rag_ctx_for_log,
        rag_timings=rag_timings,
        rag_context_data=rag_context_data,
        background_refresh_started=background_refresh_started,
        web_supplement_text=web_supplement_text,
        web_sup_meta=web_sup_meta,
    )
