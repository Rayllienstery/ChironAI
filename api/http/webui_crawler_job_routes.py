"""Crawler crawl subprocess and create-collection job routes."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Callable

from error_manager.http import error_response as _error_response
from flask import current_app, jsonify, request

from api.http.webui_crawler_helpers import is_safe_identifier
from api.http.webui_crawler_indexing_helpers import (
    import_qdrant as _import_qdrant,
)
from api.http.webui_crawler_indexing_helpers import (
    write_create_collection_final_log as _write_create_collection_final_log,
)
from api.http.webui_crawler_indexing_runtime_core import (
    _collection_jobs,
    _collection_jobs_lock,
    create_collection_from_sources,
    touch_collection_job_timing,
)
from config import get_indexing_int, get_qdrant_url
from core.shared.correlation import log_operation, resolve_correlation_id
from infrastructure.database import get_settings_repository
from webui_backend.paths import webui_data_dir

try:
    from modules.md_indexer import get_active_pipeline_name
except ImportError:
    get_active_pipeline_name = None  # type: ignore[assignment,misc]

_ERROR_LOG: Any = None
_WEBUI_LOG = logging.getLogger("webui")


def register_crawler_job_routes(
    bp,
    *,
    error_log,
    root: str,
    webui_backend: str,
    get_crawler_sources_dir: Callable[[], str],
    load_source_meta: Callable[[str], dict | None],
    load_sources_config: Callable[[], list[dict]],
    save_sources_config: Callable[[list[dict]], bool],
) -> None:
    global _ERROR_LOG
    _ERROR_LOG = error_log
    _ROOT = root
    _WEBUI_BACKEND = webui_backend

    # Track crawling processes
    _crawling_processes: dict[str, subprocess.Popen] = {}


    @bp.route("/crawler/sources/<source_id>/crawl", methods=["POST"])
    def crawl_source_endpoint(source_id: str) -> Any:
        """Start crawling a specific source. Returns immediately, crawl runs in background."""
        try:
            # Check if source exists
            meta = load_source_meta(source_id)
            if not meta:
                # For now, we'll allow crawling even if meta doesn't exist
                # The crawl will create it
                pass
    
            # Check if already crawling
            if source_id in _crawling_processes:
                proc = _crawling_processes[source_id]
                if proc.poll() is None:  # Still running
                    return jsonify({
                        "status": "already_running",
                        "message": f"Crawl for source '{source_id}' is already in progress"
                    }), 409
    
            correlation_id = resolve_correlation_id()
            log_operation(
                _WEBUI_LOG,
                logging.INFO,
                operation="crawler.crawl.start",
                correlation_id=correlation_id,
                message=f"Starting crawl for source '{source_id}'",
                source_id=source_id,
            )

            # Run crawl in subprocess
            env = os.environ.copy()
            env["CHIRONAI_CORRELATION_ID"] = correlation_id
            env["CHIRONAI_PROJECT_ROOT"] = _ROOT
            env["CHIRONAI_WEBUI_DIR"] = str(webui_data_dir())
            _extra_path = os.pathsep.join(
                [
                    _ROOT,
                    _WEBUI_BACKEND,
                    os.path.join(_ROOT, "modules", "crawler_service"),
                    os.path.join(_ROOT, "modules", "html_md"),
                ]
            )
            env["PYTHONPATH"] = _extra_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "crawler_service.api.cli",
                    "crawl",
                    "--source",
                    source_id,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=_ROOT,
                env=env,
            )
            _crawling_processes[source_id] = proc
    
            # Clean up finished processes
            finished = [sid for sid, p in _crawling_processes.items() if p.poll() is not None]
            for sid in finished:
                del _crawling_processes[sid]
    
            return jsonify({
                "status": "started",
                "source_id": source_id,
                "correlation_id": correlation_id,
                "message": f"Crawl started for source '{source_id}'"
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.crawl_source_endpoint", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>/crawl/status", methods=["GET"])
    def get_crawl_status(source_id: str) -> Any:
        """Get status of crawling process for a source."""
        try:
            if source_id not in _crawling_processes:
                return jsonify({
                    "status": "not_running",
                    "source_id": source_id,
                })
    
            proc = _crawling_processes[source_id]
            return_code = proc.poll()
    
            if return_code is None:
                return jsonify({
                    "status": "running",
                    "source_id": source_id,
                })
            else:
                # Process finished: capture stderr for failed runs, then clean up
                stderr_preview = None
                try:
                    if proc.stderr:
                        err = proc.stderr.read()
                        if err:
                            stderr_preview = err.decode("utf-8", errors="replace").strip()
                            if len(stderr_preview) > 2000:
                                stderr_preview = "... " + stderr_preview[-2000:]
                except Exception:  # safe: stderr read is best-effort after subprocess exit
                    pass
                del _crawling_processes[source_id]
                out = {
                    "status": "finished",
                    "source_id": source_id,
                    "return_code": return_code,
                }
                if stderr_preview:
                    out["stderr"] = stderr_preview
                return jsonify(out)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawl_status", exc_info=True)
            return _error_response(e)




    def run_create_collection_job(
        job_id: str,
        app_context: Any,
        collection_name: str,
        source_ids: list[str],
        chunk_max_size: int,
        chunk_min_size: int,
        embed_provider_id: str | None = None,
        embed_model: str | None = None,
        parallel_embed_workers: int | None = None,
    ) -> None:
        """Background task: run indexing and update job progress."""
        with app_context:
            correlation_id = ""
            with _collection_jobs_lock:
                job = _collection_jobs.get(job_id)
                if job:
                    correlation_id = str(job.get("correlation_id") or job_id)
            log_operation(
                _WEBUI_LOG,
                logging.INFO,
                operation="crawler.index.start",
                correlation_id=correlation_id or job_id,
                message=f"Create-collection job started for '{collection_name}'",
                job_id=job_id,
                collection_name=collection_name,
            )

            def should_cancel() -> bool:
                with _collection_jobs_lock:
                    job = _collection_jobs.get(job_id)
                    return bool(job and job.get("cancel_requested"))

            def on_progress(processed: int, total: int, st: dict[str, Any]) -> None:
                with _collection_jobs_lock:
                    if job_id in _collection_jobs:
                        job = _collection_jobs[job_id]
                        now = time.perf_counter()
                        next_phase = st.get("current_phase", "")
                        if next_phase != job.get("current_phase", ""):
                            job["_phase_started_perf"] = now - (
                                float(st.get("current_phase_elapsed_ms") or 0) / 1000
                            )
                        job["processed_pages"] = processed
                        job["total_pages"] = total
                        job["indexed_pages"] = st.get("indexed_pages", 0)
                        job["prepared_pages"] = st.get("prepared_pages", 0)
                        job["total_chunks"] = st.get("total_chunks", 0)
                        job["prepared_chunks"] = st.get("prepared_chunks", 0)
                        job["skipped_pages"] = st.get("skipped_pages", 0)
                        job["errors"] = list(st.get("errors", [])[-8:])
                        job["recent_skips"] = list(st.get("recent_skips", [])[-8:])
                        job["skip_log"] = list(st.get("skip_log", []))
                        job["largest_prepare_removals"] = list(
                            st.get("largest_prepare_removals", [])[:8]
                        )
                        sr = st.get("skip_reasons") or {}
                        job["skip_reasons"] = dict(sr)
                        job["current_source_id"] = st.get("current_source_id", "")
                        job["current_filename"] = st.get("current_filename", "")
                        job["current_phase"] = next_phase
                        job["last_skip_reason"] = st.get("last_skip_reason", "")
                        job["cancelled"] = bool(st.get("cancelled", False))
                        job["deduped_chunks"] = st.get("deduped_chunks", 0)
                        job["embed_dropped_chunks"] = st.get("embed_dropped_chunks", 0)
                        job["prepare_original_chars"] = st.get("prepare_original_chars", 0)
                        job["prepare_output_chars"] = st.get("prepare_output_chars", 0)
                        job["prepare_removed_chars"] = st.get("prepare_removed_chars", 0)
                        job["empty_after_prepare_removed_chars"] = st.get(
                            "empty_after_prepare_removed_chars",
                            0,
                        )
                        job["current_embedding_chars"] = st.get("current_embedding_chars", 0)
                        job["current_embedding_chunks"] = st.get("current_embedding_chunks", 0)
                        job["current_embedding_chunk_ms"] = st.get(
                            "current_embedding_chunk_ms",
                            0,
                        )
                        job["embedding_history"] = list(st.get("embedding_history", [])[:8])
                        job["elapsed_ms"] = st.get("elapsed_ms", 0)
                        job["current_phase_elapsed_ms"] = st.get(
                            "current_phase_elapsed_ms",
                            0,
                        )
                        job["phase_durations_ms"] = dict(st.get("phase_durations_ms") or {})

            try:
                stats = create_collection_from_sources(
                    collection_name=collection_name,
                    source_ids=source_ids,
                    chunk_max_size=chunk_max_size,
                    chunk_min_size=chunk_min_size,
                    on_progress=on_progress,
                    embed_provider_id=embed_provider_id,
                    embed_model=embed_model,
                    parallel_embed_workers=parallel_embed_workers,
                    should_cancel=should_cancel,
                )
                cancelled = bool(stats.get("cancelled"))
                with _collection_jobs_lock:
                    if job_id in _collection_jobs:
                        cancelled = cancelled or bool(_collection_jobs[job_id].get("cancel_requested"))
                        _collection_jobs[job_id]["status"] = "cancelled" if cancelled else "success"
                        _collection_jobs[job_id]["statistics"] = stats
                        _collection_jobs[job_id]["processed_pages"] = (
                            _collection_jobs[job_id].get("processed_pages", 0)
                            if cancelled
                            else stats.get("total_pages", 0)
                        )
                        _collection_jobs[job_id]["indexed_pages"] = stats.get("indexed_pages", 0)
                        _collection_jobs[job_id]["prepared_pages"] = stats.get("prepared_pages", 0)
                        _collection_jobs[job_id]["total_chunks"] = stats.get("total_chunks", 0)
                        _collection_jobs[job_id]["prepared_chunks"] = stats.get("prepared_chunks", 0)
                        _collection_jobs[job_id]["skipped_pages"] = stats.get("skipped_pages", 0)
                        _collection_jobs[job_id]["skip_reasons"] = dict(stats.get("skip_reasons") or {})
                        _collection_jobs[job_id]["errors"] = list(stats.get("errors", [])[-8:])
                        _collection_jobs[job_id]["recent_skips"] = list(stats.get("recent_skips", [])[-8:])
                        _collection_jobs[job_id]["skip_log"] = list(stats.get("skip_log", []))
                        _collection_jobs[job_id]["largest_prepare_removals"] = list(
                            stats.get("largest_prepare_removals", [])[:8]
                        )
                        _collection_jobs[job_id]["current_phase"] = "cancelled" if cancelled else "complete"
                        _collection_jobs[job_id]["current_source_id"] = ""
                        _collection_jobs[job_id]["current_filename"] = ""
                        _collection_jobs[job_id]["cancelled"] = cancelled
                        _collection_jobs[job_id]["deduped_chunks"] = stats.get("deduped_chunks", 0)
                        _collection_jobs[job_id]["embed_dropped_chunks"] = stats.get("embed_dropped_chunks", 0)
                        _collection_jobs[job_id]["prepare_original_chars"] = stats.get("prepare_original_chars", 0)
                        _collection_jobs[job_id]["prepare_output_chars"] = stats.get("prepare_output_chars", 0)
                        _collection_jobs[job_id]["prepare_removed_chars"] = stats.get("prepare_removed_chars", 0)
                        _collection_jobs[job_id]["empty_after_prepare_removed_chars"] = stats.get(
                            "empty_after_prepare_removed_chars",
                            0,
                        )
                        _collection_jobs[job_id]["current_embedding_chars"] = stats.get("current_embedding_chars", 0)
                        _collection_jobs[job_id]["current_embedding_chunks"] = stats.get("current_embedding_chunks", 0)
                        _collection_jobs[job_id]["current_embedding_chunk_ms"] = stats.get(
                            "current_embedding_chunk_ms",
                            0,
                        )
                        _collection_jobs[job_id]["embedding_history"] = list(stats.get("embedding_history", [])[:8])
                        _collection_jobs[job_id]["elapsed_ms"] = stats.get("elapsed_ms", 0)
                        _collection_jobs[job_id]["current_phase_elapsed_ms"] = stats.get(
                            "current_phase_elapsed_ms",
                            0,
                        )
                        _collection_jobs[job_id]["phase_durations_ms"] = dict(stats.get("phase_durations_ms") or {})
                _write_create_collection_final_log(
                    job_id=job_id,
                    collection_name=collection_name,
                    source_ids=source_ids,
                    status="cancelled" if cancelled else "success",
                    stats={
                        **stats,
                        "processed_pages": stats.get("total_pages", 0)
                        if not cancelled
                        else stats.get("processed_pages", 0),
                    },
                )
                if not cancelled and not stats.get("cancelled"):
                    try:
                        from datetime import datetime, timezone

                        settings_repo = get_settings_repository()
                        embed_label = (embed_model or "").strip() or "default"
                        indexed_at = (
                            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        )
                        settings_repo.set_collection_meta(
                            collection_name,
                            framework_id=",".join(source_ids),
                            version=embed_label,
                            last_refreshed_at=indexed_at,
                        )
                        pipeline_name = (
                            get_active_pipeline_name() if get_active_pipeline_name else "default"
                        )
                        index_meta = {
                            "embed_model": embed_label,
                            "indexed_at": indexed_at,
                            "pipeline_version": pipeline_name,
                            "source_ids": list(source_ids),
                            "points_count": stats.get("total_chunks", 0),
                            "prepared_pages": stats.get("prepared_pages", 0),
                            "prepared_chunks": stats.get("prepared_chunks", 0),
                            "deduped_chunks": stats.get("deduped_chunks", 0),
                            "embed_dropped_chunks": stats.get("embed_dropped_chunks", 0),
                            "elapsed_ms": stats.get("elapsed_ms", 0),
                            "phase_durations_ms": dict(stats.get("phase_durations_ms") or {}),
                        }
                        settings_repo.set_app_setting(
                            f"rag_collection_index_meta:{collection_name}",
                            json.dumps(index_meta, ensure_ascii=False),
                        )
                    except Exception:  # safe: index meta persistence failure must not abort job
                        _ERROR_LOG.warning(
                            "Failed to persist collection meta for %s",
                            collection_name,
                            exc_info=True,
                        )
            except Exception as e:
                _ERROR_LOG.error("webui_crawler_routes.create_collection job", exc_info=True)
                failed_stats: dict[str, Any] = {}
                with _collection_jobs_lock:
                    if job_id in _collection_jobs:
                        _collection_jobs[job_id]["status"] = "failed"
                        _collection_jobs[job_id]["error"] = str(e)
                        failed_stats = dict(_collection_jobs[job_id])
                _write_create_collection_final_log(
                    job_id=job_id,
                    collection_name=collection_name,
                    source_ids=source_ids,
                    status="failed",
                    stats=failed_stats,
                    error=str(e),
                )


    @bp.route("/crawler/create-collection-status/<job_id>", methods=["GET"])
    def get_create_collection_status(job_id: str) -> Any:
        """Return progress or result of a create-collection job."""
        with _collection_jobs_lock:
            job = _collection_jobs.get(job_id)
            if job:
                touch_collection_job_timing(job)
                job = dict(job)
        if not job:
            return _error_response("Job not found", 404, extra={"job_id": job_id})
        statistics = job.get("statistics")
        is_running = job.get("status", "running") == "running"
        skip_log_count = (
            len(statistics.get("skip_log") or [])
            if isinstance(statistics, dict)
            else len(job.get("skip_log") or [])
        )
        full_skip_log = list(job.get("recent_skips") or []) if is_running else (
            list(statistics.get("skip_log") or [])
            if isinstance(statistics, dict)
            else list(job.get("skip_log") or [])
        )
        phase_durations_ms = dict(job.get("phase_durations_ms") or {})
        current_phase = str(job.get("current_phase") or "")
        if is_running and current_phase:
            phase_durations_ms[current_phase] = int(phase_durations_ms.get(current_phase, 0) or 0) + int(
                job.get("current_phase_elapsed_ms", 0) or 0
            )
        return jsonify({
            "job_id": job_id,
            "status": job.get("status", "running"),
            "collection_name": job.get("collection_name", ""),
            "source_ids": job.get("source_ids", []),
            "processed_pages": job.get("processed_pages", 0),
            "total_pages": job.get("total_pages", 0),
            "indexed_pages": job.get("indexed_pages", 0),
            "prepared_pages": job.get("prepared_pages", 0),
            "total_chunks": job.get("total_chunks", 0),
            "prepared_chunks": job.get("prepared_chunks", 0),
            "skipped_pages": job.get("skipped_pages", 0),
            "skip_reasons": job.get("skip_reasons", {}),
            "current_source_id": job.get("current_source_id", ""),
            "current_filename": job.get("current_filename", ""),
            "current_phase": job.get("current_phase", ""),
            "last_skip_reason": job.get("last_skip_reason", ""),
            "cancel_requested": bool(job.get("cancel_requested", False)),
            "cancelled": bool(job.get("cancelled", False)),
            "errors": job.get("errors", []),
            "recent_skips": job.get("recent_skips", []),
            "skip_log": full_skip_log,
            "skip_log_count": skip_log_count,
            "largest_prepare_removals": job.get("largest_prepare_removals", []),
            "deduped_chunks": job.get("deduped_chunks", 0),
            "embed_dropped_chunks": job.get("embed_dropped_chunks", 0),
            "prepare_original_chars": job.get("prepare_original_chars", 0),
            "prepare_output_chars": job.get("prepare_output_chars", 0),
            "prepare_removed_chars": job.get("prepare_removed_chars", 0),
            "empty_after_prepare_removed_chars": job.get("empty_after_prepare_removed_chars", 0),
            "current_embedding_chars": job.get("current_embedding_chars", 0),
            "current_embedding_chunks": job.get("current_embedding_chunks", 0),
            "current_embedding_chunk_ms": job.get("current_embedding_chunk_ms", 0),
            "embedding_history": job.get("embedding_history", []),
            "parallel_embed_workers": job.get("parallel_embed_workers", 0),
            "elapsed_ms": job.get("elapsed_ms", 0),
            "current_phase_elapsed_ms": job.get("current_phase_elapsed_ms", 0),
            "phase_durations_ms": phase_durations_ms,
            "statistics": job.get("statistics"),
            "error": job.get("error"),
        })


    @bp.route("/crawler/create-collection-cancel/<job_id>", methods=["POST"])
    def cancel_create_collection(job_id: str) -> Any:
        """Request cooperative cancellation for a running create-collection job."""
        with _collection_jobs_lock:
            job = _collection_jobs.get(job_id)
            if not job:
                return _error_response("Job not found", 404, extra={"job_id": job_id})
            status = job.get("status", "running")
            if status != "running":
                return jsonify({
                    "job_id": job_id,
                    "status": status,
                    "cancel_requested": bool(job.get("cancel_requested", False)),
                })
            job["cancel_requested"] = True
            job["current_phase"] = "cancelling"
            job["_phase_started_perf"] = time.perf_counter()
        return jsonify({
            "job_id": job_id,
            "status": "running",
            "cancel_requested": True,
        })


    @bp.route("/crawler/create-collection", methods=["POST"])
    def create_collection() -> Any:
        """Start creating a Qdrant collection (async). Returns job_id; poll create-collection-status for progress."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            collection_name = body.get("collection_name", "").strip()
            source_ids = body.get("source_ids", [])
            chunk_max_size = int(body.get("chunk_max_size", 1200))
            chunk_min_size = int(body.get("chunk_min_size", 300))
            embed_provider_id = str(body.get("rag_embed_provider_id") or "").strip()
            embed_model_raw = str(body.get("rag_embed_model") or "").strip()
            embed_model = embed_model_raw or None
            parallel_embed_workers = max(
                1,
                min(8, int(body.get("parallel_embed_workers") or get_indexing_int("embed_parallel_workers", 4))),
            )

            if not collection_name:
                return _error_response("collection_name is required", 400)

            if not source_ids:
                return _error_response("At least one source_id is required", 400)

            if not is_safe_identifier(collection_name):
                return _error_response("Collection name must contain only alphanumeric characters, underscores, and hyphens", 400)

            qdrant_url = get_qdrant_url().rstrip("/")
            QdrantClient, _, _, _, _, _ = _import_qdrant()
            qclient = QdrantClient(url=qdrant_url)
            try:
                qclient.get_collection(collection_name)
                return _error_response(f"Collection '{collection_name}' already exists", 409)
            except Exception:  # safe: Qdrant 404 means collection absent — proceed with create
                pass

            available_sources = []
            for source_id in source_ids:
                meta = load_source_meta(source_id)
                if meta and meta.get("pages"):
                    available_sources.append(source_id)
                else:
                    return jsonify({
                        "error": f"Source '{source_id}' has no crawled pages. Please crawl the source first."
                    }), 400

            if not available_sources:
                return jsonify({
                    "error": "None of the specified sources have crawled pages. Please crawl sources first."
                }), 400

            job_id = str(uuid.uuid4())
            correlation_id = resolve_correlation_id()
            total_pages = 0
            for sid in available_sources:
                meta = load_source_meta(sid)
                if meta and meta.get("pages"):
                    total_pages += len(meta.get("pages", {}))

            with _collection_jobs_lock:
                started_perf = time.perf_counter()
                _collection_jobs[job_id] = {
                    "status": "running",
                    "correlation_id": correlation_id,
                    "_started_perf": started_perf,
                    "_phase_started_perf": started_perf,
                    "collection_name": collection_name,
                    "source_ids": list(available_sources),
                    "processed_pages": 0,
                    "total_pages": total_pages,
                    "indexed_pages": 0,
                    "prepared_pages": 0,
                    "total_chunks": 0,
                    "prepared_chunks": 0,
                    "skipped_pages": 0,
                    "errors": [],
                    "recent_skips": [],
                    "skip_log": [],
                    "largest_prepare_removals": [],
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
                    "cancel_requested": False,
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
                    "parallel_embed_workers": parallel_embed_workers,
                    "elapsed_ms": 0,
                    "current_phase_elapsed_ms": 0,
                    "phase_durations_ms": {},
                }

            thread = threading.Thread(
                target=run_create_collection_job,
                args=(
                    job_id,
                    current_app.app_context(),
                    collection_name,
                    available_sources,
                    chunk_max_size,
                    chunk_min_size,
                    embed_provider_id or None,
                    embed_model,
                    parallel_embed_workers,
                ),
                daemon=True,
            )
            thread.start()

            return jsonify({
                "job_id": job_id,
                "correlation_id": correlation_id,
                "status": "started",
                "collection_name": collection_name,
            }), 202

        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.create_collection", exc_info=True)
            return _error_response(e)



__all__ = ["register_crawler_job_routes"]
