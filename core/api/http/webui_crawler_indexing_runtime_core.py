"""Crawler indexing runtime: page processing and collection build."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing
from rag_service.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from rag_service.domain.services.metadata_inference import (
    _apple_doc_scope_from_doc_kind,
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)

from api.http.rag_sources_meta import update_page_chunk_hashes
from api.http.webui_crawler_helpers import get_crawler_sources_dir, load_source_meta
from api.http.webui_crawler_indexing_helpers import import_qdrant as _import_qdrant
from api.http.webui_crawler_indexing_runtime_embed import (
    authority_tier,
    ensure_collection_with_name,
    get_embeddings_simple,
    is_hub_url,
    material_class,
    point_id_from_hash,
    qdrant_collection_has_sparse_vectors,
    sha256_text,
)
from api.http.webui_crawler_source_config import load_sources_config
from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from config import get_indexing_int, get_qdrant_url
from infrastructure.rag.qdrant_point_builder import build_named_vectors

if TYPE_CHECKING:
    from qdrant_client.http.models import PointStruct

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_WEBUI_LOG = logging.getLogger("webui")

_collection_jobs: dict[str, dict[str, Any]] = {}
_collection_jobs_lock = threading.Lock()

def touch_collection_job_timing(job: dict[str, Any]) -> None:
    if job.get("status", "running") != "running":
        return
    now = time.perf_counter()
    started_perf = float(job.setdefault("_started_perf", now))
    phase_started_perf = float(job.setdefault("_phase_started_perf", now))
    job["elapsed_ms"] = int((now - started_perf) * 1000)
    job["current_phase_elapsed_ms"] = (
        int((now - phase_started_perf) * 1000)
        if job.get("current_phase")
        else 0
    )


def snapshot_indexing_stats(st: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy for progress callbacks (skip_reasons copied so callers see fresh counts)."""
    timing_touch = st.get("_touch_timing")
    if callable(timing_touch):
        timing_touch()
    snap = dict(st)
    snap["skip_reasons"] = dict(st.get("skip_reasons") or {})
    snap["errors"] = list(st.get("errors") or [])
    snap["recent_skips"] = list(st.get("recent_skips") or [])
    snap["largest_prepare_removals"] = list(st.get("largest_prepare_removals") or [])
    snap["embedding_history"] = list(st.get("embedding_history") or [])
    snap.pop("_touch_timing", None)
    return snap


def record_prepare_stats(st: dict[str, Any], prepare_stats: dict[str, Any] | None) -> None:
    ps = prepare_stats or {}
    original_chars = int(ps.get("body_original_chars") or 0)
    prepared_chars = int(ps.get("body_prepared_chars") or 0)
    removed_chars = int(ps.get("removed_chars") or 0)
    st["prepare_original_chars"] = int(st.get("prepare_original_chars") or 0) + original_chars
    st["prepare_output_chars"] = int(st.get("prepare_output_chars") or 0) + prepared_chars
    st["prepare_removed_chars"] = int(st.get("prepare_removed_chars") or 0) + removed_chars


def remember_prepare_removal(
    st: dict[str, Any],
    *,
    source_id: str,
    filename: str,
    prepare_stats: dict[str, Any] | None,
) -> None:
    ps = prepare_stats or {}
    removed_chars = int(ps.get("removed_chars") or 0)
    if removed_chars <= 0:
        return
    rows = st.setdefault("largest_prepare_removals", [])
    rows.append(
        {
            "source_id": source_id,
            "filename": filename,
            "removed_chars": removed_chars,
            "original_chars": int(ps.get("body_original_chars") or 0),
            "prepared_chars": int(ps.get("body_prepared_chars") or 0),
        }
    )
    rows.sort(key=lambda item: int(item.get("removed_chars") or 0), reverse=True)
    del rows[8:]


def remember_embedding_history(
    st: dict[str, Any],
    *,
    source_id: str,
    filename: str,
    prepared_chars: int,
    chunk_count: int,
    chunk_ms: int = 0,
    status: str = "embedding",
    reason: str = "",
    detail: str = "",
) -> None:
    path = f"{source_id}/{filename}".lstrip("/")
    row = {
        "source_id": source_id,
        "filename": filename,
        "path": path,
        "chars": int(prepared_chars or 0),
        "chunks": int(chunk_count or 0),
        "chunk_ms": int(chunk_ms or 0),
        "status": status,
        "reason": reason,
        "detail": detail,
    }
    st["current_embedding_chars"] = row["chars"]
    st["current_embedding_chunks"] = row["chunks"]
    st["current_embedding_chunk_ms"] = row["chunk_ms"]
    rows = st.setdefault("embedding_history", [])
    if rows and rows[0].get("path") == path:
        rows[0] = row
    else:
        rows.insert(0, row)
    del rows[8:]


def record_page_skip(
    st: dict[str, Any],
    reason: str,
    error_msg: str | None = None,
    *,
    source_id: str = "",
    filename: str = "",
    detail: str | None = None,
    prepare_stats: dict[str, Any] | None = None,
) -> None:
    st["skipped_pages"] += 1
    sr = st.setdefault(
        "skip_reasons",
        {
            "read_error": 0,
            "too_short": 0,
            "filename_excluded": 0,
            "content_excluded": 0,
            "empty_after_prepare": 0,
            "chunk_failed": 0,
            "no_valid_chunks": 0,
            "embed_failed": 0,
            "dim_mismatch": 0,
            "other": 0,
        },
    )
    if reason in sr:
        sr[reason] += 1
    else:
        sr["other"] = sr.get("other", 0) + 1
    st["last_skip_reason"] = reason
    if source_id or filename or detail or error_msg:
        ps = prepare_stats or {}
        skip_entry = {
            "source_id": source_id,
            "filename": filename,
            "reason": reason,
            "detail": detail or error_msg or "",
            "removed_chars": int(ps.get("removed_chars") or 0),
            "original_chars": int(ps.get("body_original_chars") or 0),
            "prepared_chars": int(ps.get("body_prepared_chars") or 0),
        }
        st.setdefault("skip_log", []).append(skip_entry)
        recent = st.setdefault("recent_skips", [])
        recent.append(skip_entry)
        del recent[:-12]
        status = "error" if reason in {"read_error", "chunk_failed", "embed_failed", "dim_mismatch"} else "skipped"
        remember_embedding_history(
            st,
            source_id=source_id,
            filename=filename,
            prepared_chars=int(ps.get("body_prepared_chars") or 0),
            chunk_count=0,
            status=status,
            reason=reason,
            detail=detail or error_msg or "",
        )
    if error_msg:
        errs = st.setdefault("errors", [])
        errs.append(error_msg)
def create_collection_from_sources(
    collection_name: str,
    source_ids: list[str],
    chunk_max_size: int,
    chunk_min_size: int,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
    *,
    embed_provider_id: str | None = None,
    embed_model: str | None = None,
    parallel_embed_workers: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Create a Qdrant collection by indexing pages from specified sources.
    Returns statistics about the indexing process.
    If on_progress is set, called as on_progress(processed_count, total_pages, stats) after each page.
    """
    sources_dir = get_crawler_sources_dir()
    qdrant_url = get_qdrant_url().rstrip("/")
    QdrantClient, _, _, PointStruct, _, _ = _import_qdrant()
    qclient = QdrantClient(url=qdrant_url)

    stats: dict[str, Any] = {
        "total_pages": 0,
        "indexed_pages": 0,
        "prepared_pages": 0,
        "total_chunks": 0,
        "prepared_chunks": 0,
        "skipped_pages": 0,
        "errors": [],
        "skip_reasons": {
            "read_error": 0,
            "too_short": 0,
            "filename_excluded": 0,
            "content_excluded": 0,
            "empty_after_prepare": 0,
            "chunk_failed": 0,
            "no_valid_chunks": 0,
            "embed_failed": 0,
            "dim_mismatch": 0,
            "other": 0,
        },
        "current_source_id": "",
        "current_filename": "",
        "current_phase": "",
        "last_skip_reason": "",
        "cancelled": False,
        "deduped_chunks": 0,
        "embed_dropped_chunks": 0,
        "prepare_original_chars": 0,
        "prepare_output_chars": 0,
        "prepare_removed_chars": 0,
        "empty_after_prepare_removed_chars": 0,
        "current_embedding_chars": 0,
        "current_embedding_chunks": 0,
        "current_embedding_chunk_ms": 0,
        "embedding_history": [],
        "parallel_embed_workers": max(1, min(8, int(parallel_embed_workers or get_indexing_int("embed_parallel_workers", 4)))),
        "recent_skips": [],
        "skip_log": [],
        "largest_prepare_removals": [],
        "elapsed_ms": 0,
        "current_phase_elapsed_ms": 0,
        "phase_durations_ms": {},
    }

    run_started_perf = time.perf_counter()
    phase_started_perf = run_started_perf

    def _touch_timing() -> None:
        now = time.perf_counter()
        stats["elapsed_ms"] = int((now - run_started_perf) * 1000)
        if stats.get("current_phase"):
            stats["current_phase_elapsed_ms"] = int((now - phase_started_perf) * 1000)
        else:
            stats["current_phase_elapsed_ms"] = 0

    def _set_phase(phase: str) -> None:
        nonlocal phase_started_perf
        now = time.perf_counter()
        prev = str(stats.get("current_phase") or "")
        if prev and prev != phase:
            durations = stats.setdefault("phase_durations_ms", {})
            durations[prev] = int(durations.get(prev, 0) or 0) + int((now - phase_started_perf) * 1000)
            phase_started_perf = now
        elif not prev:
            phase_started_perf = now
        stats["current_phase"] = phase
        stats["current_phase_elapsed_ms"] = 0
        stats["elapsed_ms"] = int((now - run_started_perf) * 1000)

    def _finish_timing() -> None:
        prev = str(stats.get("current_phase") or "")
        if prev:
            now = time.perf_counter()
            durations = stats.setdefault("phase_durations_ms", {})
            durations[prev] = int(durations.get(prev, 0) or 0) + int((now - phase_started_perf) * 1000)
        _touch_timing()

    stats["_touch_timing"] = _touch_timing

    hybrid_cfg = is_hybrid_sparse_enabled()
    effective_hybrid = False

    first_dim: int | None = None
    upsert_batch: list[PointStruct] = []
    BATCH_SIZE = max(50, get_indexing_int("batch_upsert_size", 200))
    seen_chunk_keys: set[str] = set()
    chunk_overlap = get_indexing_int("chunk_overlap", 150)
    embed_batch_size = max(1, get_indexing_int("embed_batch_size", 32))
    embed_window_chunks = max(embed_batch_size, get_indexing_int("embed_window_chunks", embed_batch_size * 4))

    config_sources = {s.get("id"): s for s in load_sources_config(_ROOT) if s.get("id")}
    source_extras: dict[str, dict[str, Any]] = {
        sid: (cfg.get("extra") or {}) if isinstance(cfg.get("extra"), dict) else {}
        for sid, cfg in config_sources.items()
    }

    # Collect all pages from specified sources
    candidates: list[tuple[str, str, dict, str, dict]] = []  # (source_id, filename, entry, pages_dir, source_meta)

    for source_id in source_ids:
        source_meta = load_source_meta(source_id)
        if not source_meta:
            stats["errors"].append(f"Source '{source_id}' not found or has no metadata")
            continue
    
        pages_meta = source_meta.get("pages", {})
        if not pages_meta:
            continue
    
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        if not os.path.isdir(pages_dir):
            continue
    
        for filename, entry in pages_meta.items():
            candidates.append((source_id, filename, entry, pages_dir, source_meta))

    # Index high-value sources first so partial runs are useful (Apple docs before WWDC transcripts).
    _INDEX_SOURCE_PRIORITY = {
        "apple_documentation": 0,
        "swift_book": 1,
        "hws_swift": 2,
        "objc_io_issues": 3,
        "swiftbysundell_articles": 4,
        "pointfree_collections": 5,
        "wwdc_sessions_2019_plus": 9,
    }
    candidates.sort(
        key=lambda item: (
            _INDEX_SOURCE_PRIORITY.get(item[0], 50),
            item[0],
            item[1],
        )
    )

    stats["total_pages"] = len(candidates)

    if not candidates:
        _finish_timing()
        stats.pop("_touch_timing", None)
        return stats

    processed = 0
    total_pages = len(candidates)
    pending_pages: list[dict[str, Any]] = []

    def _pending_chunk_count() -> int:
        return sum(len(page.get("chunks_with_paths") or []) for page in pending_pages)

    def _flush_upsert_batch(*, final: bool = False) -> None:
        if not upsert_batch:
            return
        if not final and len(upsert_batch) < BATCH_SIZE:
            return
        try:
            qclient.upsert(collection_name=collection_name, points=upsert_batch)
            upsert_batch.clear()
        except Exception as e:
            stats["errors"].append(f"Failed to upsert {'final ' if final else ''}batch: {e}")

    def _mark_page_processed() -> None:
        nonlocal processed
        processed += 1
        _set_phase("idle")
        if on_progress:
            on_progress(processed, total_pages, snapshot_indexing_stats(stats))

    def _skip_pending_page(page: dict[str, Any], reason: str, detail: str) -> None:
        record_page_skip(
            stats,
            reason,
            f"{page['source_id']}/{page['filename']}: {detail}",
            source_id=page["source_id"],
            filename=page["filename"],
            detail=detail,
            prepare_stats=page.get("prepare_stats"),
        )
        _mark_page_processed()

    def _store_embedded_page(page: dict[str, Any], embeddings: list[list[float] | None]) -> bool:
        nonlocal first_dim, effective_hybrid
        source_id = page["source_id"]
        filename = page["filename"]
        entry = page["entry"]
        source_meta = page["source_meta"]
        page_meta = page["page_meta"]
        chunks_with_paths = page["chunks_with_paths"]
        prepare_stats = page.get("prepare_stats")

        if should_cancel and should_cancel():
            stats["cancelled"] = True
            _set_phase("cancelled")
            if on_progress:
                on_progress(processed, total_pages, snapshot_indexing_stats(stats))
            return False

        if not embeddings:
            _skip_pending_page(page, "embed_failed", "no embeddings returned")
            return True

        embedded_pairs = [
            ((chunk_text, section_path), vec)
            for (chunk_text, section_path), vec in zip(chunks_with_paths, embeddings)
            if vec is not None
        ]
        dropped_embedding_chunks = len(chunks_with_paths) - len(embedded_pairs)
        if dropped_embedding_chunks:
            stats["embed_dropped_chunks"] += dropped_embedding_chunks
            _WEBUI_LOG.warning(
                "Dropped %s chunks after embedding context fallback for %s/%s",
                dropped_embedding_chunks,
                source_id,
                filename,
            )
        if not embedded_pairs:
            _skip_pending_page(page, "embed_failed", "all chunks exceeded embedding context")
            return True

        chunks_with_paths = [pair for pair, _vec in embedded_pairs]
        vectors = [vec for _pair, vec in embedded_pairs]
        dim = len(vectors[0])
        if first_dim is None:
            first_dim = dim
            ensure_collection_with_name(
                qclient,
                collection_name,
                first_dim,
                hybrid_sparse=hybrid_cfg,
            )
            effective_hybrid = hybrid_cfg and qdrant_collection_has_sparse_vectors(
                qclient,
                collection_name,
            )

        if dim != first_dim:
            record_page_skip(
                stats,
                "dim_mismatch",
                f"Dimension mismatch for {source_id}/{filename}: {dim} != {first_dim}",
                source_id=source_id,
                filename=filename,
                detail=f"{dim} != {first_dim}",
                prepare_stats=prepare_stats,
            )
            _mark_page_processed()
            return True

        stats["current_source_id"] = source_id
        stats["current_filename"] = filename
        _set_phase("saving")
        if on_progress:
            on_progress(processed, total_pages, snapshot_indexing_stats(stats))

        if should_cancel and should_cancel():
            stats["cancelled"] = True
            _set_phase("cancelled")
            if on_progress:
                on_progress(processed, total_pages, snapshot_indexing_stats(stats))
            return False

        url_for_meta = page_meta.get("url") or entry.get("url")
        page_chunk_hashes: list[str] = []
        for (chunk_text, section_path), vec in zip(chunks_with_paths, vectors):
            norm_text = re.sub(r"\s+", " ", (chunk_text or "").strip())
            dedup_key = sha256_text(norm_text.casefold())
            if dedup_key in seen_chunk_keys:
                stats["deduped_chunks"] += 1
                continue
            seen_chunk_keys.add(dedup_key)

            section_path_str = ":".join(section_path) if section_path else ""
            chunk_hash = sha256_text(f"{source_id}:{filename}:{section_path_str}:{chunk_text}")
            page_chunk_hashes.append(chunk_hash)
            point_id = point_id_from_hash(chunk_hash)

            ios_versions, swift_versions = extract_versions(chunk_text)
            if page_meta.get("ios_versions"):
                ios_versions = sorted(set(ios_versions + page_meta["ios_versions"]))
            if page_meta.get("swift_versions"):
                swift_versions = sorted(set(swift_versions + page_meta["swift_versions"]))
            meta_extra = infer_metadata(
                source_id=source_id,
                filename=filename,
                url=url_for_meta,
                section_path=section_path,
                text=chunk_text,
            )
            if page_meta.get("framework"):
                meta_extra["technology"] = page_meta["framework"].lower()
            if page_meta.get("doc_kind"):
                meta_extra["doc_type"] = page_meta["doc_kind"]
            if page_meta.get("doc_scope"):
                meta_extra["doc_scope"] = page_meta["doc_scope"]
            elif source_id == "apple_documentation":
                inferred = _apple_doc_scope_from_doc_kind(page_meta.get("doc_kind"))
                if inferred:
                    meta_extra["doc_scope"] = inferred
            display_meta = infer_chunk_display_meta(section_path)
            section_path_joined = section_path_str
            payload = {
                "source": source_id,
                "url": url_for_meta or entry.get("url", ""),
                "path": f"pages/{filename}",
                "chunk_id": chunk_hash,
                "text": chunk_text,
                "section_path": section_path,
                "section_path_joined": section_path_joined,
                "ios_versions": ios_versions,
                "swift_versions": swift_versions,
                "version": source_meta.get("last_crawled"),
                **meta_extra,
            }
            payload["authority_tier"] = authority_tier(source_id)
            payload["is_hub"] = bool(is_hub_url(source_id, url_for_meta or entry.get("url", "")))
            payload["material_class"] = material_class(source_id, url_for_meta or entry.get("url", ""))
            if page_meta.get("framework"):
                payload["framework"] = page_meta["framework"]
            if display_meta.get("symbol"):
                payload["symbol"] = display_meta["symbol"]
            if display_meta.get("section"):
                payload["section"] = display_meta["section"]
            payload["token_count"] = estimate_token_count(chunk_text)

            upsert_batch.append(
                PointStruct(
                    id=point_id,
                    vector=build_named_vectors(
                        chunk_text,
                        vec,
                        hybrid_sparse=effective_hybrid,
                    ),
                    payload=payload,
                )
            )
            stats["total_chunks"] += 1

        _flush_upsert_batch()
        stats["indexed_pages"] += 1
        try:
            update_page_chunk_hashes(source_id, filename, page_chunk_hashes)
        except Exception:
            _WEBUI_LOG.warning(
                "Failed to persist chunk_hashes for %s/%s",
                source_id,
                filename,
                exc_info=True,
            )
        _mark_page_processed()
        return True

    def _flush_pending_pages() -> bool:
        if not pending_pages:
            return True
        if should_cancel and should_cancel():
            stats["cancelled"] = True
            _set_phase("cancelled")
            if on_progress:
                on_progress(processed, total_pages, snapshot_indexing_stats(stats))
            pending_pages.clear()
            return False

        all_embed_texts: list[str] = []
        for page in pending_pages:
            remember_embedding_history(
                stats,
                source_id=page["source_id"],
                filename=page["filename"],
                prepared_chars=page["prepared_chars"],
                chunk_count=len(page["chunks_with_paths"]),
                chunk_ms=page.get("chunk_ms", 0),
            )
            all_embed_texts.extend(page["embed_texts"])

        first_page = pending_pages[0]
        stats["current_source_id"] = first_page["source_id"]
        stats["current_filename"] = first_page["filename"]
        _set_phase("embedding")
        if on_progress:
            on_progress(processed, total_pages, snapshot_indexing_stats(stats))

        try:
            all_embeddings = get_embeddings_simple(
                all_embed_texts,
                embed_provider_id=embed_provider_id,
                embed_model_override=embed_model,
                parallel_workers=parallel_embed_workers,
            )
        except Exception as batch_error:
            _WEBUI_LOG.warning(
                "Embedding window failed; retrying per page (pages=%s, chunks=%s): %s",
                len(pending_pages),
                len(all_embed_texts),
                batch_error,
            )
            for page in pending_pages:
                try:
                    page_embeddings = get_embeddings_simple(
                        page["embed_texts"],
                        embed_provider_id=embed_provider_id,
                        embed_model_override=embed_model,
                        parallel_workers=parallel_embed_workers,
                    )
                except Exception as page_error:
                    _skip_pending_page(page, "embed_failed", str(page_error))
                    continue
                if not _store_embedded_page(page, page_embeddings):
                    pending_pages.clear()
                    return False
            pending_pages.clear()
            return True

        offset = 0
        for page in pending_pages:
            count = len(page["embed_texts"])
            page_embeddings = all_embeddings[offset : offset + count]
            offset += count
            if not _store_embedded_page(page, page_embeddings):
                pending_pages.clear()
                return False
        pending_pages.clear()
        return True

    # Process each page
    for source_id, filename, entry, pages_dir, source_meta in candidates:
        if should_cancel and should_cancel():
            stats["cancelled"] = True
            _set_phase("cancelled")
            if on_progress:
                on_progress(processed, total_pages, snapshot_indexing_stats(stats))
            break

        page_path = os.path.join(pages_dir, filename)
        stats["current_source_id"] = source_id
        stats["current_filename"] = filename
        _set_phase("reading")
        stats["last_skip_reason"] = ""
        if on_progress:
            on_progress(processed, total_pages, snapshot_indexing_stats(stats))

        try:
            with open(page_path, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception as e:
            record_page_skip(
                stats,
                "read_error",
                f"Failed to read {source_id}/{filename}: {e}",
                source_id=source_id,
                filename=filename,
                detail=str(e),
            )
            _mark_page_processed()
            continue

        _set_phase("prepare")
        prep = prepare_markdown_for_indexing(
            filename,
            md,
            source_extra=source_extras.get(source_id),
        )
        record_prepare_stats(stats, prep.prepare_stats)
        remember_prepare_removal(
            stats,
            source_id=source_id,
            filename=filename,
            prepare_stats=prep.prepare_stats,
        )
        if prep.skipped:
            if (prep.skip_reason or "") == "empty_after_prepare":
                stats["empty_after_prepare_removed_chars"] += int(
                    (prep.prepare_stats or {}).get("removed_chars") or 0
                )
            detail = prep.skip_detail or prep.skip_reason or "skipped"
            record_page_skip(
                stats,
                prep.skip_reason or "other",
                f"{source_id}/{filename}: {detail}",
                source_id=source_id,
                filename=filename,
                detail=detail,
                prepare_stats=prep.prepare_stats,
            )
            _mark_page_processed()
            continue

        page_meta = dict(prep.page_meta or {})
        for key in ("framework", "doc_kind", "doc_scope", "url"):
            val = entry.get(key) if isinstance(entry, dict) else None
            if val and not page_meta.get(key):
                page_meta[key] = val
        md = prep.body_md

        # Split into chunks
        _set_phase("chunking")
        chunk_started_perf = time.perf_counter()
        try:
            chunks_with_paths = split_markdown_into_chunks(
                md,
                max_chunk_size=chunk_max_size,
                min_chunk_size=chunk_min_size,
                chunk_overlap=chunk_overlap,
            )
            chunks_with_paths = [
                (t, p) for t, p in chunks_with_paths if chunk_quality_ok(t, source_id=source_id)
            ]
            chunk_ms = int((time.perf_counter() - chunk_started_perf) * 1000)
        except Exception as e:
            chunk_ms = int((time.perf_counter() - chunk_started_perf) * 1000)
            record_page_skip(
                stats,
                "chunk_failed",
                f"Failed to chunk {source_id}/{filename}: {e}",
                source_id=source_id,
                filename=filename,
                detail=str(e),
                prepare_stats=prep.prepare_stats,
            )
            _mark_page_processed()
            continue

        if not chunks_with_paths:
            record_page_skip(
                stats,
                "no_valid_chunks",
                f"{source_id}/{filename}: no quality chunks after filtering",
                source_id=source_id,
                filename=filename,
                detail="no quality chunks after filtering",
                prepare_stats=prep.prepare_stats,
            )
            _mark_page_processed()
            continue

        embed_texts = [
            build_embed_prefix(page_meta, sp) + t
            for t, sp in chunks_with_paths
        ]
        stats["prepared_pages"] += 1
        stats["prepared_chunks"] += len(chunks_with_paths)
        pending_pages.append(
            {
                "source_id": source_id,
                "filename": filename,
                "entry": entry,
                "source_meta": source_meta,
                "page_meta": page_meta,
                "chunks_with_paths": chunks_with_paths,
                "embed_texts": embed_texts,
                "prepare_stats": prep.prepare_stats,
                "prepared_chars": len(md or ""),
                "chunk_ms": chunk_ms,
            }
        )
        if on_progress:
            on_progress(processed, total_pages, snapshot_indexing_stats(stats))
        if _pending_chunk_count() >= embed_window_chunks and not _flush_pending_pages():
            break

    _flush_pending_pages()

    # Flush remaining batch
    _flush_upsert_batch(final=True)
    _set_phase("cancelled" if stats.get("cancelled") else "complete")
    _finish_timing()
    stats.pop("_touch_timing", None)

    return stats


__all__ = [
    "_collection_jobs",
    "_collection_jobs_lock",
    "create_collection_from_sources",
    "touch_collection_job_timing",
]
