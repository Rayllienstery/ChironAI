"""RAG collection and project-context prep helpers for chat completions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from llm_proxy.chat_completions_response_helpers import proxy_settings_optional_int


def build_framework_name_to_collection_map(rag_sources_config: list[Any]) -> dict[str, str]:
    """Map framework trigger keywords and external_source_id to Qdrant collection names."""
    name_to_collection: dict[str, str] = {}
    for cfg in rag_sources_config:
        trigger_keywords = getattr(cfg, "trigger_keywords", None) or []
        for kw in trigger_keywords:
            key = (kw or "").strip().lower()
            if key:
                name_to_collection[key] = cfg.collection_name
        external_id = (getattr(cfg, "external_source_id", None) or "").strip()
        if external_id:
            name_to_collection[external_id.lower()] = cfg.collection_name
    return name_to_collection


def resolve_framework_collection_ttl_days(
    settings_repo: Any | None,
    *,
    default_ttl_days: int,
) -> int:
    if settings_repo is None:
        return default_ttl_days
    try:
        ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
        if ttl_raw is not None and str(ttl_raw).strip() != "":
            return int(ttl_raw)
    except (TypeError, ValueError):
        pass
    except Exception:
        pass
    return default_ttl_days


def resolve_project_fresh_collections(
    frameworks: list[Any],
    *,
    name_to_collection: dict[str, str],
    settings_repo: Any | None,
    check_collection_freshness: Callable[[dict[str, str] | None, int], str],
    default_ttl_days: int,
) -> tuple[set[str] | None, list[tuple[str, str]]]:
    """
    Resolve fresh framework-linked collections and those needing background refresh.

    Returns:
        (fresh_collection_names, needs_refresh) where needs_refresh entries are
        (framework_id_lower, collection_name).
    """
    if not frameworks or not name_to_collection:
        return None, []

    ttl_days = resolve_framework_collection_ttl_days(
        settings_repo,
        default_ttl_days=default_ttl_days,
    )
    fresh_collections: list[str] = []
    needs_refresh: list[tuple[str, str]] = []
    for fw in frameworks:
        if not isinstance(fw, dict):
            continue
        name = (fw.get("name") or "").strip()
        if not name:
            continue
        coll = name_to_collection.get(name.lower())
        if not coll:
            continue
        meta = None
        if settings_repo is not None:
            try:
                meta = settings_repo.get_collection_meta(coll)
            except Exception:
                pass
        if check_collection_freshness(meta, ttl_days) == "fresh":
            if coll not in fresh_collections:
                fresh_collections.append(coll)
        else:
            needs_refresh.append((name.lower(), coll))
    fresh_names = set(fresh_collections) if fresh_collections else None
    return fresh_names, needs_refresh


def apply_proxy_context_char_limits(
    proxy_settings: dict[str, Any],
    *,
    effective_context_chunk_chars: int,
    effective_context_total_chars: int,
) -> tuple[int, int, int | None]:
    """Overlay proxy_settings context limits; returns (chunk_chars, total_chars, rag_top_k)."""
    chunk_chars = effective_context_chunk_chars
    total_chars = effective_context_total_chars
    chunk_override = proxy_settings_optional_int(proxy_settings, "context_chunk_chars", 64, 500_000)
    if chunk_override is not None:
        chunk_chars = chunk_override
    total_override = proxy_settings_optional_int(proxy_settings, "context_total_chars", 256, 2_000_000)
    if total_override is not None:
        total_chars = total_override
    rag_top_k = proxy_settings_optional_int(proxy_settings, "rag_top_k", 1, 256)
    return chunk_chars, total_chars, rag_top_k


def build_rag_metadata_for_response(rag_ctx: Any) -> dict[str, object]:
    """Build OpenAI response rag_metadata from a RAG context object."""
    payload: dict[str, object] = {
        "chunks_info": rag_ctx.chunks_info,
        "max_score": rag_ctx.max_score,
        "chunks_count": len(rag_ctx.chunks_info),
    }
    rag_trace = getattr(rag_ctx, "rag_trace", None)
    if isinstance(rag_trace, list):
        payload["rag_trace"] = rag_trace
    coverage_report = getattr(rag_ctx, "coverage_report", None)
    if isinstance(coverage_report, dict):
        payload["coverage_report"] = coverage_report
    rag_quality = getattr(rag_ctx, "rag_quality", None)
    if isinstance(rag_quality, dict):
        payload["rag_quality"] = rag_quality
    return payload


def build_rag_context_log_snapshot(rag_ctx_for_log: Any | None) -> dict[str, Any] | None:
    if not rag_ctx_for_log:
        return None
    return {
        "chunks_count": len(rag_ctx_for_log.chunks_info),
        "max_score": rag_ctx_for_log.max_score,
        "context_length": len(rag_ctx_for_log.context_text),
        "chunks_info": rag_ctx_for_log.chunks_info[:5] if rag_ctx_for_log.chunks_info else [],
    }


def enrich_rag_trace_for_ui(
    trace: dict[str, Any],
    *,
    rag_ctx_for_log: Any | None,
    rag_timings: dict[str, float] | None,
    effective_context_total_chars: int,
    background_refresh_started: bool,
) -> None:
    """Populate trace rag/internet fields and RAG sub-step timeline for the UI."""
    rag_timings = rag_timings or {}
    trace["rag"]["timings"] = dict(rag_timings)
    trace["internet"].update(
        {
            "fetch_s": float(rag_timings.get("fetch_s", 0.0) or 0.0),
            "discovery_s": float(rag_timings.get("discovery_s", 0.0) or 0.0),
        }
    )
    trace["internet"]["used"] = bool(
        rag_timings.get("fetch_s")
        or rag_timings.get("discovery_s")
        or background_refresh_started
    )
    if rag_ctx_for_log:
        trace["rag"]["context"] = {
            "context_chars_used": len(rag_ctx_for_log.context_text or ""),
            "context_budget_chars": int(effective_context_total_chars or 0),
            "context_text_preview": (rag_ctx_for_log.context_text or "")[:2000],
            "chunks": rag_ctx_for_log.chunks_info[:20] if rag_ctx_for_log.chunks_info else [],
        }
        trace["rag"]["tokens_estimates"] = {
            "embed_tokens_in": rag_timings.get("embed_tokens_in"),
            "rerank_prompt_tokens_in": rag_timings.get("rerank_prompt_tokens_in"),
            "fetch_tokens_in": rag_timings.get("fetch_tokens_in"),
            "discovery_tokens_in": rag_timings.get("discovery_tokens_in"),
        }
    else:
        trace["rag"]["context"] = None

    steps: list[dict[str, object]] = []

    def _add_step(name: str, dur_s: float, tokens_in_est: object | None = None) -> None:
        if dur_s and dur_s > 0:
            steps.append(
                {
                    "name": name,
                    "duration_ms": int(dur_s * 1000),
                    "tokens_in_est": tokens_in_est,
                    "tokens_out_est": 0,
                }
            )

    _add_step("embed", float(rag_timings.get("embed_s", 0.0) or 0.0), rag_timings.get("embed_tokens_in"))
    _add_step("search", float(rag_timings.get("search_s", 0.0) or 0.0), None)
    _add_step("rerank", float(rag_timings.get("rerank_s", 0.0) or 0.0), rag_timings.get("rerank_prompt_tokens_in"))
    _add_step("fetch", float(rag_timings.get("fetch_s", 0.0) or 0.0), rag_timings.get("fetch_tokens_in"))
    _add_step("discovery", float(rag_timings.get("discovery_s", 0.0) or 0.0), rag_timings.get("discovery_tokens_in"))
    _add_step("total_rag", float(rag_timings.get("total_rag_s", 0.0) or 0.0), None)
    trace["steps"] = steps
