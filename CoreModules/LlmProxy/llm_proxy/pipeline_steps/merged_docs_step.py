"""Merged docs (external_docs_rag) step for LLM proxy pipeline."""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MergedDocsStepMeta:
    id: str = "merged_docs"
    icon: str = "cloud_download"
    title: str = "Merged docs"
    description: str = "Merge external docs retrieval (on-demand/discovery + RAG) when enabled."


@dataclass
class MergedDocsStepResult:
    used: bool
    rag_ctx_for_log: Any | None
    rag_timings: dict[str, float]
    background_refresh_started: bool
    status: str
    reason: str | None = None


def run_merged_docs_step(
    *,
    w: Any,
    last_user: str,
    messages: list[dict[str, Any]],
    body: dict[str, Any],
    fetch_web_knowledge: bool,
    request_collection: str | None,
    effective_embed_provider: Any,
    effective_context_chunk_chars: int,
    effective_context_total_chars: int,
    project_fresh_collection_names: set[str] | None,
    needs_refresh: list[tuple[str, str]],
    logger: Any,
) -> MergedDocsStepResult:
    default_timings = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
    if not fetch_web_knowledge:
        return MergedDocsStepResult(
            used=False,
            rag_ctx_for_log=None,
            rag_timings=default_timings,
            background_refresh_started=False,
            status="disabled",
            reason="fetch_web_knowledge_off",
        )
    if request_collection:
        return MergedDocsStepResult(
            used=False,
            rag_ctx_for_log=None,
            rag_timings=default_timings,
            background_refresh_started=False,
            status="disabled",
            reason="explicit_collection",
        )
    if not (
        w.external_docs.available
        and w.external_docs.load_rag_sources_config
        and w.external_docs.resolve_rag_sources_for_request
        and w.external_docs.build_merged_rag_context
        and w.external_docs.qdrant_rag_search_adapter_cls is not None
    ):
        return MergedDocsStepResult(
            used=False,
            rag_ctx_for_log=None,
            rag_timings=default_timings,
            background_refresh_started=False,
            status="disabled",
            reason="external_docs_unavailable",
        )

    rag_sources_config = w.external_docs.load_rag_sources_config()
    body_rag_sources = body.get("rag_sources")
    body_rag_sources = [str(x) for x in body_rag_sources] if isinstance(body_rag_sources, list) else None
    resolved = w.external_docs.resolve_rag_sources_for_request(last_user, messages, body_rag_sources, rag_sources_config)
    if len(resolved) < 1:
        return MergedDocsStepResult(
            used=False,
            rag_ctx_for_log=None,
            rag_timings=default_timings,
            background_refresh_started=False,
            status="disabled",
            reason="no_resolved_sources",
        )

    background_refresh_started = False
    # Trigger full crawl for resolved sources that are missing or stale when repo is on GitHub.
    try:
        _settings_repo = w.get_settings_repository()
        _ttl_days = w.get_framework_collection_ttl_days()
        _ttl_raw = _settings_repo.get_app_setting("framework_collection_ttl_days")
        if _ttl_raw is not None and str(_ttl_raw).strip() != "":
            with contextlib.suppress(TypeError, ValueError):
                _ttl_days = int(_ttl_raw)
    except Exception:
        _settings_repo = None
        _ttl_days = 90
    resolved_needs_refresh: list[tuple[str, str]] = []
    if _settings_repo:
        for cfg in resolved:
            meta = None
            with contextlib.suppress(Exception):
                meta = _settings_repo.get_collection_meta(cfg.collection_name)
            if w.check_collection_freshness(meta, _ttl_days) != "fresh":
                fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower() or cfg.collection_name.lower()
                resolved_needs_refresh.append((fid, cfg.collection_name))
    work_list = list(needs_refresh)
    for (fid, coll) in resolved_needs_refresh:
        if coll not in [c for _, c in work_list]:
            work_list.append((fid, coll))
    if (
        work_list
        and w.external_docs.load_github_repos
        and w.external_docs.ingest_github_repo_markdown
        and w.external_docs.http_fetch_client_cls
        and w.external_docs.qdrant_chunk_sink_cls
        and w.external_docs.get_latest_release_tag
    ):
        coll_to_framework_id = {}
        for cfg in rag_sources_config:
            fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower()
            if fid:
                coll_to_framework_id[cfg.collection_name] = fid
        github_repos_list = w.external_docs.load_github_repos()
        by_framework_id = {(e.get("framework_id") or "").lower(): e for e in github_repos_list if e.get("framework_id")}

        def _run_refresh(work: list) -> None:
            try:
                qdrant_url = w.get_qdrant_url()
                fetch_client = w.external_docs.http_fetch_client_cls()
                chunk_sink = w.external_docs.qdrant_chunk_sink_cls(base_url=qdrant_url)
                repo = w.get_settings_repository()

                def on_indexed(cname: str, fid: str, ver: str | None, last_at: str) -> None:
                    repo.set_collection_meta(cname, fid, ver or "", last_at)

                for _name, coll in work:
                    fid = coll_to_framework_id.get(coll) or coll.lower()
                    entry = by_framework_id.get(fid)
                    if not entry:
                        continue
                    owner = entry.get("owner", "")
                    repo_name = entry.get("repo", "")
                    ref = entry.get("ref") or "main"
                    if ref in ("latest", ""):
                        tag = w.external_docs.get_latest_release_tag(f"{owner}/{repo_name}")
                        ref = tag or "main"
                    w.external_docs.ingest_github_repo_markdown(
                        owner,
                        repo_name,
                        ref,
                        coll,
                        fid,
                        fetch_client,
                        chunk_sink,
                        effective_embed_provider,
                        max_depth=3,
                        on_indexed=on_indexed,
                    )
                    break
            except Exception as e:
                logger.warning("Background framework refresh failed: %s", e)

        background_refresh_started = True
        threading.Thread(target=_run_refresh, args=(work_list,), daemon=True).start()

    try:
        qdrant_url = w.get_qdrant_url()
    except Exception:
        qdrant_url = "http://localhost:6333"
    rag_search_adapter = w.external_docs.qdrant_rag_search_adapter_cls(base_url=qdrant_url)
    fetch_client = w.external_docs.http_fetch_client_cls() if w.external_docs.http_fetch_client_cls is not None else None
    external_sources_list = w.external_docs.load_external_sources() if w.external_docs.load_external_sources else []
    merged_ctx, merged_timings = w.external_docs.build_merged_rag_context(
        last_user,
        resolved,
        rag_search_adapter,
        effective_embed_provider,
        effective_context_chunk_chars,
        effective_context_total_chars,
        fetch_client=fetch_client,
        external_sources=external_sources_list,
        fresh_collection_names=project_fresh_collection_names,
    )
    rag_ctx_for_log = w.rag_context_factory(
        context_text=merged_ctx.context_text,
        chunks_info=merged_ctx.chunks_info,
        max_score=merged_ctx.max_score,
    )
    return MergedDocsStepResult(
        used=True,
        rag_ctx_for_log=rag_ctx_for_log,
        rag_timings=merged_timings,
        background_refresh_started=background_refresh_started,
        status="executed",
        reason=None,
    )


__all__ = ["MergedDocsStepMeta", "MergedDocsStepResult", "run_merged_docs_step"]
