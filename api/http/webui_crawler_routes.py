"""Crawler, source inspection, indexer tester, and collection routes."""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request

from error_manager.http import error_response as _error_response
from webui_backend.paths import webui_data_dir
from config import (
    get_indexing_int,
    get_qdrant_url,
)
from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from rag_service.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from rag_service.domain.services.metadata_inference import (
    _apple_doc_scope_from_doc_kind,
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)
from rag_service.application.params import get_rag_answer_params
from infrastructure.database import get_logs_repository, get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from infrastructure.rag.qdrant_point_builder import (
    build_named_vectors,
    dense_vectors_config,
    hybrid_vectors_config,
)
from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing

# qdrant_client is loaded lazily inside functions that use it to avoid the
# ~800ms startup cost when crawling/indexing is not actively in use.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        PointStruct,
    )


def _import_qdrant() -> tuple[type, type, type, type, type, type]:
    """Lazy-load qdrant_client types. Returns (QdrantClient, Distance, PayloadSchemaType, PointStruct, SparseVectorParams, VectorParams)."""
    from qdrant_client import QdrantClient as _QC  # noqa: PLC0415
    from qdrant_client.http.models import (  # noqa: PLC0415
        Distance as _Dist,
        PayloadSchemaType as _PST,
        PointStruct as _PS,
        SparseVectorParams as _SVP,
        VectorParams as _VP,
    )
    return _QC, _Dist, _PST, _PS, _SVP, _VP

from api.http.rag_sources_meta import update_page_chunk_hashes
from api.http.webui_crawler_helpers import is_safe_identifier
from api.http.webui_crawler_source_routes import register_crawler_source_routes
from api.http.webui_provider_helpers import (
    default_llm_provider_id as _default_llm_provider_id,
    invoke_runtime_chat as _invoke_runtime_chat,
    invoke_runtime_embed as _invoke_runtime_embed,
)
from api.http.webui_rag_routes import get_qdrant_collection_names as _get_qdrant_collection_names

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WEBUI_BACKEND = os.path.join(_ROOT, "CoreModules", "WebUIBackend")
if os.path.isdir(_WEBUI_BACKEND) and _WEBUI_BACKEND not in sys.path:
    sys.path.insert(0, _WEBUI_BACKEND)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()


def _create_collection_log_metadata(
    *,
    job_id: str,
    collection_name: str,
    source_ids: list[str],
    status: str,
    stats: dict[str, Any],
    error: str = "",
) -> dict[str, Any]:
    """Build the final create-collection log payload shared by UI logs and file logs."""
    return {
        "job_id": job_id,
        "collection_name": collection_name,
        "source_ids": list(source_ids),
        "status": status,
        "error": error,
        "processed_pages": stats.get("processed_pages", stats.get("total_pages", 0)),
        "total_pages": stats.get("total_pages", 0),
        "indexed_pages": stats.get("indexed_pages", 0),
        "prepared_pages": stats.get("prepared_pages", 0),
        "skipped_pages": stats.get("skipped_pages", 0),
        "total_chunks": stats.get("total_chunks", 0),
        "prepared_chunks": stats.get("prepared_chunks", 0),
        "deduped_chunks": stats.get("deduped_chunks", 0),
        "embed_dropped_chunks": stats.get("embed_dropped_chunks", 0),
        "parallel_embed_workers": stats.get("parallel_embed_workers", 0),
        "skip_reasons": dict(stats.get("skip_reasons") or {}),
        "prepare_original_chars": stats.get("prepare_original_chars", 0),
        "prepare_output_chars": stats.get("prepare_output_chars", 0),
        "prepare_removed_chars": stats.get("prepare_removed_chars", 0),
        "empty_after_prepare_removed_chars": stats.get("empty_after_prepare_removed_chars", 0),
        "elapsed_ms": stats.get("elapsed_ms", 0),
        "current_phase_elapsed_ms": stats.get("current_phase_elapsed_ms", 0),
        "phase_durations_ms": dict(stats.get("phase_durations_ms") or {}),
        "embedding_history": list(stats.get("embedding_history") or []),
        "recent_skips": list(stats.get("recent_skips") or []),
        "skip_log": list(stats.get("skip_log") or stats.get("recent_skips") or []),
        "largest_prepare_removals": list(stats.get("largest_prepare_removals") or []),
        "errors": list(stats.get("errors") or []),
    }


def _write_create_collection_final_log(
    *,
    job_id: str,
    collection_name: str,
    source_ids: list[str],
    status: str,
    stats: dict[str, Any],
    error: str = "",
) -> None:
    metadata = _create_collection_log_metadata(
        job_id=job_id,
        collection_name=collection_name,
        source_ids=source_ids,
        status=status,
        stats=stats,
        error=error,
    )
    message = (
        f"Create collection {status}: {collection_name}; "
        f"indexed={metadata['indexed_pages']} skipped={metadata['skipped_pages']} "
        f"chunks={metadata['total_chunks']} issues={len(metadata['skip_log'])} "
        f"duration_ms={metadata.get('elapsed_ms', 0)}"
    )
    if error:
        message = f"{message}; error={error}"
    _WEBUI_LOG.info("%s metadata=%s", message, json.dumps(metadata, ensure_ascii=False))
    try:
        get_logs_repository().add_log(
            session_id="system",
            level="ERROR" if status == "failed" else "INFO",
            source="crawler",
            message=message,
            error_type="CreateCollectionFailed" if status == "failed" else None,
            metadata=metadata,
        )
    except Exception:
        _WEBUI_LOG.debug("Failed to persist create-collection final log", exc_info=True)

try:
    from modules.md_indexer import (
        delete_pipeline as md_indexer_delete_pipeline,
        get_active_pipeline_name,
        list_pipeline_names,
        load_pipeline,
        run_pipeline,
        save_pipeline,
    )
except ImportError:
    md_indexer_delete_pipeline = None  # type: ignore[assignment]
    get_active_pipeline_name = None  # type: ignore[assignment]
    list_pipeline_names = None  # type: ignore[assignment]
    load_pipeline = None  # type: ignore[assignment]
    run_pipeline = None  # type: ignore[assignment]
    save_pipeline = None  # type: ignore[assignment]


def _config_default_embed_model() -> str:
    try:
        from config import get_default_embed_model

        return str(get_default_embed_model() or "").strip()
    except Exception:
        return os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")


_DEFAULT_MAX_EMBED_CHARS = 1_800


def _max_embed_chars() -> int:
    return max(256, get_indexing_int("embed_truncate_chars", _DEFAULT_MAX_EMBED_CHARS))


def _clip_text_for_embedding(text: str, max_chars: int | None = None) -> str:
    """Clip embed input at a readable boundary before provider context checks."""
    value = text or ""
    limit = max_chars if max_chars is not None else _max_embed_chars()
    if len(value) <= limit:
        return value
    clipped = value[:limit].rstrip()
    min_break = max(160, int(limit * 0.55))
    breakpoints = (
        (clipped.rfind("\n\n"), 0),
        (clipped.rfind("\n"), 0),
        (clipped.rfind(". "), 1),
        (clipped.rfind(" "), 0),
    )
    for idx, keep_chars in breakpoints:
        if idx >= min_break:
            clipped = clipped[: idx + keep_chars].rstrip()
            break
    if clipped.count("```") % 2:
        fence_idx = clipped.rfind("```")
        if fence_idx > 0:
            clipped = clipped[:fence_idx].rstrip()
    return clipped or value[:limit].strip()


def _is_embed_context_length_error(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return "context length" in text or "input length exceeds" in text


def _runtime_embed_available() -> bool:
    """True when Flask app has extension runtime or llm_proxy wiring (not plain webui_backend.app)."""
    try:
        from flask import has_app_context, current_app

        if not has_app_context():
            return False
        if current_app.extensions.get("llm_proxy_wiring") is not None:
            return True
        from api.http.extensions_service_access import get_extensions_runtime

        return get_extensions_runtime(current_app) is not None
    except Exception:
        return False


_INDEXING_EMBED_PATH_LOGGED = False


def _log_indexing_embed_path_once(path: str) -> None:
    global _INDEXING_EMBED_PATH_LOGGED
    if _INDEXING_EMBED_PATH_LOGGED:
        return
    _INDEXING_EMBED_PATH_LOGGED = True
    _WEBUI_LOG.info("Create-collection embedding path: %s", path)


def register_crawler_routes(bp: Blueprint, *, error_log: Any) -> None:
    global _ERROR_LOG
    _ERROR_LOG = error_log
    # Crawler / Indexer API Endpoints
    # ============================================================================

    def _get_crawler_sources_dir() -> str:
        """Get path to WebUI/rag_sources directory."""
        return str(webui_data_dir() / "rag_sources")


    def _load_source_meta(source_id: str) -> dict | None:
        """Load meta.json for a source. Returns None if not found."""
        sources_dir = _get_crawler_sources_dir()
        meta_path = os.path.join(sources_dir, source_id, "meta.json")
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("source_id", source_id)
            data.setdefault("source_url", "")
            data.setdefault("last_crawled", None)
            data.setdefault("hash_algo", "sha256")
            data.setdefault("pages", {})
            return data
        except Exception as e:
            _WEBUI_LOG.warning(f"Failed to load meta.json for {source_id}: {e}")
            return None


    def _get_source_stats(meta: dict) -> dict[str, Any]:
        """Calculate statistics from meta.json."""
        pages = meta.get("pages", {})
        total_pages = len(pages)
        indexed_pages = sum(
            1 for p in pages.values() 
            if p.get("chunk_hashes") and len(p.get("chunk_hashes", [])) > 0
        )
        return {
            "total_pages": total_pages,
            "indexed_pages": indexed_pages,
            "last_crawled": meta.get("last_crawled"),
        }


    def _discover_sources() -> list[str]:
        """Scan WebUI/rag_sources directory to find all source IDs."""
        sources_dir = _get_crawler_sources_dir()
        if not os.path.isdir(sources_dir):
            return []
        source_ids = []
        for item in os.listdir(sources_dir):
            item_path = os.path.join(sources_dir, item)
            if os.path.isdir(item_path):
                meta_path = os.path.join(item_path, "meta.json")
                if os.path.isfile(meta_path):
                    source_ids.append(item)
        return sorted(source_ids)


    def _sha256(text: str) -> str:
        """Compute SHA256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _authority_tier(source_id: str) -> int:
        # 3 = official Apple docs, 2 = language guide (swift_book), 1 = community, 0 = WWDC
        if source_id == "apple_documentation":
            return 3
        if source_id == "swift_book":
            return 2
        if source_id.startswith("wwdc_sessions_"):
            return 0
        return 1

    def _is_hub_url(source_id: str, url: str) -> bool:
        u = (url or "").strip().lower().rstrip("/")
        if not u:
            return False
        if source_id == "hws_swift":
            return u in (
                "https://www.hackingwithswift.com/quick-start/swiftui",
                "https://www.hackingwithswift.com/read",
                "https://www.hackingwithswift.com/example-code",
            )
        if source_id == "pointfree_collections":
            return u.endswith("/collections") or u.endswith("/collections/swiftui/state-management")
        return False

    def _material_class(source_id: str, url: str) -> str:
        if source_id == "apple_documentation":
            return "official"
        if source_id == "swift_book":
            return "swift_book"
        if source_id.startswith("wwdc_sessions_"):
            return "wwdc"
        if _is_hub_url(source_id, url):
            return "hub"
        return "community"


    def _point_id_from_hash(h: str) -> int:
        """Build a Qdrant-compatible unsigned integer point id from a sha256 hex string."""
        h = (h or "0" * 16)[:16]
        return int(h, 16)


    def _get_embeddings_simple(
        texts: list[str],
        *,
        embed_provider_id: str | None = None,
        embed_model_override: str | None = None,
        parallel_workers: int | None = None,
    ) -> list[list[float] | None]:
        """Simple embedding function using the configured blind runtime provider.

        When ``embed_model_override`` is non-empty, it is used for this call only
        (e.g. create-collection job). Otherwise: app_settings, then env, then default.
        """
        if not texts:
            return []

        resolved_provider_id = str(embed_provider_id or "").strip()
        if not resolved_provider_id:
            try:
                settings_repo = get_settings_repository()
                resolved_provider_id = str(settings_repo.get_app_setting("rag_embed_provider_id") or "").strip()
            except Exception:
                resolved_provider_id = ""
        if not resolved_provider_id:
            resolved_provider_id = _default_llm_provider_id()

        override = (embed_model_override or "").strip()
        if override:
            embed_model = override
        else:
            try:
                settings_repo = get_settings_repository()
                raw = settings_repo.get_app_setting("rag_embed_model")
                rag_embed_model = (raw or "").strip()
            except Exception:
                rag_embed_model = ""

            # Fallback order:
            # 1) app_settings.rag_embed_model (set from WebUI)
            # 2) legacy default embed model from config/env
            embed_model = rag_embed_model or _config_default_embed_model()

        max_embed_chars = _max_embed_chars()
        clipped_texts = [_clip_text_for_embedding(t or "", max_embed_chars) for t in texts]
        batch_size = max(1, get_indexing_int("embed_batch_size", 32))
        worker_count = max(1, min(8, int(parallel_workers or get_indexing_int("embed_parallel_workers", 4))))

        def _embed_batch_runtime(batch: list[str]) -> list[list[float]]:
            if not _runtime_embed_available():
                raise RuntimeError(
                    "Embedding provider runtime is unavailable; enable a provider extension "
                    "or configure rag_embed_provider_id."
                )
            vectors = _invoke_runtime_embed(
                provider_id=resolved_provider_id,
                model=embed_model,
                texts=batch,
            )
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"Embedding provider returned {len(vectors)} vectors for {len(batch)} texts."
                )
            return vectors

        def _embed_all() -> list[list[float] | None]:
            def _embed_batch(batch: list[str]) -> list[list[float]]:
                return _embed_batch_runtime(batch)

            def _embed_one_with_context_retry(text: str) -> list[float] | None:
                retry_limits = [min(len(text), n) for n in (1200, 900, 600, 360)]
                for limit in retry_limits:
                    clipped = _clip_text_for_embedding(text, limit)
                    try:
                        vectors = _embed_batch([clipped])
                        return vectors[0] if vectors else None
                    except Exception as e:
                        if not _is_embed_context_length_error(e):
                            raise
                _WEBUI_LOG.warning(
                    "Dropping one indexing chunk after repeated embedding context-length failures "
                    "(chars=%s, clipped_chars=%s, model=%s)",
                    len(text or ""),
                    len(_clip_text_for_embedding(text, retry_limits[-1] if retry_limits else 0)),
                    embed_model,
                )
                return None

            def _embed_adaptive(batch: list[str]) -> list[list[float] | None]:
                try:
                    return _embed_batch(batch)
                except Exception as e:
                    if not _is_embed_context_length_error(e):
                        raise
                    if len(batch) <= 1:
                        return [_embed_one_with_context_retry(batch[0])]
                    mid = max(1, len(batch) // 2)
                    _WEBUI_LOG.warning(
                        "Embedding batch exceeded provider context; splitting batch "
                        "(batch_size=%s, left=%s, right=%s, model=%s): %s",
                        len(batch),
                        mid,
                        len(batch) - mid,
                        embed_model,
                        e,
                    )
                    return _embed_adaptive(batch[:mid]) + _embed_adaptive(batch[mid:])

            out: list[list[float] | None] = []
            batches = [
                clipped_texts[i : i + batch_size]
                for i in range(0, len(clipped_texts), batch_size)
            ]
            if worker_count <= 1 or len(batches) <= 1:
                for batch in batches:
                    out.extend(_embed_adaptive(batch))
                return out
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="crawler-embed") as pool:
                for batch_vectors in pool.map(_embed_adaptive, batches):
                    out.extend(batch_vectors)
            return out

        _log_indexing_embed_path_once(f"extension LLM runtime (workers={worker_count})")

        try:
            return _embed_all()
        except Exception as first_err:
            _WEBUI_LOG.error("Embedding failed for indexing: %s", first_err)
            raise RuntimeError(f"Embedding failed during indexing: {first_err}") from first_err


    def _qdrant_collection_has_sparse_vectors(qclient: QdrantClient, collection_name: str) -> bool:
        """True if collection was created with sparse_vectors (hybrid indexing)."""
        try:
            info = qclient.get_collection(collection_name)
            params = info.config.params
            sv = getattr(params, "sparse_vectors", None)
            if sv is None:
                return False
            if isinstance(sv, dict):
                return len(sv) > 0
            return bool(sv)
        except Exception:
            return False


    def _ensure_collection_with_name(
        qclient: QdrantClient,
        collection_name: str,
        dim: int,
        *,
        hybrid_sparse: bool = False,
    ) -> None:
        """Create Qdrant collection with specified name if it doesn't exist."""
        _, Distance, PayloadSchemaType, _, SparseVectorParams, VectorParams = _import_qdrant()
        try:
            qclient.get_collection(collection_name)
            # Collection exists, ensure payload indexes
            try:
                index_fields = [
                    "language", "technology", "domain", "product", "doc_type", "doc_scope",
                    "symbol", "framework", "section",
                ]
                for field in index_fields:
                    try:
                        qclient.create_payload_index(
                            collection_name=collection_name,
                            field_name=field,
                            field_schema=PayloadSchemaType.KEYWORD,
                        )
                    except Exception:
                        pass  # Index may already exist
            except Exception:
                pass
            return
        except Exception:
            pass

        # Create collection (dense-only or dense+sparse hybrid)
        try:
            if hybrid_sparse:
                vectors_config, sparse_vectors_config = hybrid_vectors_config(dim)
                qclient.recreate_collection(
                    collection_name,
                    vectors_config=vectors_config,
                    sparse_vectors_config=sparse_vectors_config,
                )
                _WEBUI_LOG.info(
                    f"Created Qdrant collection '{collection_name}' (dim={dim}, hybrid sparse)"
                )
            else:
                qclient.recreate_collection(
                    collection_name,
                    vectors_config=dense_vectors_config(dim),
                )
                _WEBUI_LOG.info(f"Created Qdrant collection '{collection_name}' (dim={dim}, named dense)")
            # Ensure payload indexes on new collection
            for field in ["language", "technology", "domain", "product", "doc_type", "doc_scope", "symbol", "framework", "section"]:
                try:
                    qclient.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass
        except Exception as e:
            _WEBUI_LOG.error(f"Failed to create collection '{collection_name}': {e}")
            raise


    # In-memory job progress for create-collection (job_id -> { status, progress, ... })
    _collection_jobs: dict[str, dict[str, Any]] = {}
    _collection_jobs_lock = threading.Lock()


    def _touch_collection_job_timing(job: dict[str, Any]) -> None:
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


    def _snapshot_indexing_stats(st: dict[str, Any]) -> dict[str, Any]:
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


    def _record_prepare_stats(st: dict[str, Any], prepare_stats: dict[str, Any] | None) -> None:
        ps = prepare_stats or {}
        original_chars = int(ps.get("body_original_chars") or 0)
        prepared_chars = int(ps.get("body_prepared_chars") or 0)
        removed_chars = int(ps.get("removed_chars") or 0)
        st["prepare_original_chars"] = int(st.get("prepare_original_chars") or 0) + original_chars
        st["prepare_output_chars"] = int(st.get("prepare_output_chars") or 0) + prepared_chars
        st["prepare_removed_chars"] = int(st.get("prepare_removed_chars") or 0) + removed_chars


    def _remember_prepare_removal(
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


    def _remember_embedding_history(
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


    def _record_page_skip(
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
            _remember_embedding_history(
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


    def _create_collection_from_sources(
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
        sources_dir = _get_crawler_sources_dir()
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

        config_sources = {s.get("id"): s for s in _load_sources_config() if s.get("id")}
        source_extras: dict[str, dict[str, Any]] = {
            sid: (cfg.get("extra") or {}) if isinstance(cfg.get("extra"), dict) else {}
            for sid, cfg in config_sources.items()
        }
    
        # Collect all pages from specified sources
        candidates: list[tuple[str, str, dict, str, dict]] = []  # (source_id, filename, entry, pages_dir, source_meta)
    
        for source_id in source_ids:
            source_meta = _load_source_meta(source_id)
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
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))

        def _skip_pending_page(page: dict[str, Any], reason: str, detail: str) -> None:
            _record_page_skip(
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
                    on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
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
                _ensure_collection_with_name(
                    qclient,
                    collection_name,
                    first_dim,
                    hybrid_sparse=hybrid_cfg,
                )
                effective_hybrid = hybrid_cfg and _qdrant_collection_has_sparse_vectors(
                    qclient,
                    collection_name,
                )

            if dim != first_dim:
                _record_page_skip(
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
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))

            if should_cancel and should_cancel():
                stats["cancelled"] = True
                _set_phase("cancelled")
                if on_progress:
                    on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
                return False

            url_for_meta = page_meta.get("url") or entry.get("url")
            page_chunk_hashes: list[str] = []
            for (chunk_text, section_path), vec in zip(chunks_with_paths, vectors):
                norm_text = re.sub(r"\s+", " ", (chunk_text or "").strip())
                dedup_key = _sha256(norm_text.casefold())
                if dedup_key in seen_chunk_keys:
                    stats["deduped_chunks"] += 1
                    continue
                seen_chunk_keys.add(dedup_key)

                section_path_str = ":".join(section_path) if section_path else ""
                chunk_hash = _sha256(f"{source_id}:{filename}:{section_path_str}:{chunk_text}")
                page_chunk_hashes.append(chunk_hash)
                point_id = _point_id_from_hash(chunk_hash)

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
                payload["authority_tier"] = _authority_tier(source_id)
                payload["is_hub"] = bool(_is_hub_url(source_id, url_for_meta or entry.get("url", "")))
                payload["material_class"] = _material_class(source_id, url_for_meta or entry.get("url", ""))
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
                    on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
                pending_pages.clear()
                return False

            all_embed_texts: list[str] = []
            for page in pending_pages:
                _remember_embedding_history(
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
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))

            try:
                all_embeddings = _get_embeddings_simple(
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
                        page_embeddings = _get_embeddings_simple(
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
                    on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
                break

            page_path = os.path.join(pages_dir, filename)
            stats["current_source_id"] = source_id
            stats["current_filename"] = filename
            _set_phase("reading")
            stats["last_skip_reason"] = ""
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))

            try:
                with open(page_path, "r", encoding="utf-8") as f:
                    md = f.read()
            except Exception as e:
                _record_page_skip(
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
            _record_prepare_stats(stats, prep.prepare_stats)
            _remember_prepare_removal(
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
                _record_page_skip(
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
                _record_page_skip(
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
                _record_page_skip(
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
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            if _pending_chunk_count() >= embed_window_chunks and not _flush_pending_pages():
                break
    
        _flush_pending_pages()

        # Flush remaining batch
        _flush_upsert_batch(final=True)
        _set_phase("cancelled" if stats.get("cancelled") else "complete")
        _finish_timing()
        stats.pop("_touch_timing", None)
    
        return stats


    @bp.route("/crawler/sources", methods=["GET"])
    def get_crawler_sources() -> Any:
        """Get list of all configured crawl sources with metadata."""
        try:
            # Load sources from config/sources.yaml
            config_sources = _load_sources_config()
            config_sources_dict = {s.get("id"): s for s in config_sources}
        
            discovered_ids = set(_discover_sources())
            sources = []

            for source_id in sorted(discovered_ids):
                meta = _load_source_meta(source_id)
                if not meta:
                    continue

                stats = _get_source_stats(meta)
                source_data = {
                    "id": source_id,
                    "url": meta.get("source_url", ""),
                    "last_crawled": meta.get("last_crawled"),
                    "total_pages": stats["total_pages"],
                    "indexed_pages": stats["indexed_pages"],
                    "has_meta": True,
                }

                # Get config from sources.yaml if available, otherwise from meta
                config_source = config_sources_dict.get(source_id)
                if config_source:
                    source_data["url"] = config_source.get("url", source_data["url"])
                    source_data["max_depth"] = config_source.get("max_depth", 2)
                    source_data["crawler"] = config_source.get("crawler", "playwright")
                    source_data["doc_only"] = config_source.get("doc_only", True)
                    source_data["seed_urls"] = config_source.get("seed_urls", [])
                else:
                    # Fallback to meta.json
                    if "max_depth" in meta:
                        source_data["max_depth"] = meta["max_depth"]
                    if "crawler" in meta:
                        source_data["crawler"] = meta["crawler"]
                    if "doc_only" in meta:
                        source_data["doc_only"] = meta["doc_only"]
                    if "seed_urls" in meta:
                        source_data["seed_urls"] = meta["seed_urls"]

                sources.append(source_data)

            # Include sources from config that are not yet discovered (no rag_sources/<id>/meta.json)
            for config_source in config_sources:
                cid = config_source.get("id")
                if not cid or cid in discovered_ids:
                    continue
                source_data = {
                    "id": cid,
                    "url": config_source.get("url", ""),
                    "last_crawled": None,
                    "total_pages": 0,
                    "indexed_pages": 0,
                    "has_meta": False,
                    "max_depth": config_source.get("max_depth", 2),
                    "crawler": config_source.get("crawler", "playwright"),
                    "doc_only": config_source.get("doc_only", True),
                    "seed_urls": config_source.get("seed_urls", []),
                }
                sources.append(source_data)

            # Keep stable order: discovered first (sorted), then config-only (by id)
            sources.sort(key=lambda s: (s["id"],))

            return jsonify({"sources": sources})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_sources", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>", methods=["GET"])
    def get_crawler_source(source_id: str) -> Any:
        """Get detailed configuration for a specific source."""
        try:
            # Load from config/sources.yaml
            sources = _load_sources_config()
            source = next((s for s in sources if s.get("id") == source_id), None)
        
            if not source:
                # Fallback to meta.json
                meta = _load_source_meta(source_id)
                if not meta:
                    return _error_response("Source not found", 404)
            
                source = {
                    "id": source_id,
                    "url": meta.get("source_url", ""),
                    "max_depth": meta.get("max_depth", 2),
                    "crawler": meta.get("crawler", "playwright"),
                    "doc_only": meta.get("doc_only", True),
                    "seed_urls": meta.get("seed_urls", []),
                }
        
            return jsonify(source)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>/pages", methods=["GET"])
    def get_crawler_source_pages(source_id: str) -> Any:
        """Get detailed page list for a source."""
        try:
            meta = _load_source_meta(source_id)
            if not meta:
                return _error_response("Source not found", 404)
        
            pages = meta.get("pages", {})
            page_list = []
            for filename, page_data in pages.items():
                page_list.append({
                    "filename": filename,
                    "url": page_data.get("url", ""),
                    "last_updated": page_data.get("last_updated"),
                    "has_chunks": bool(page_data.get("chunk_hashes")),
                    "chunk_count": len(page_data.get("chunk_hashes", [])),
                })
        
            # Sort by last_updated descending
            page_list.sort(key=lambda x: x["last_updated"] or "", reverse=True)
        
            return jsonify({
                "source_id": source_id,
                "pages": page_list,
                "total": len(page_list),
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source_pages", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/sources", methods=["GET"])
    def get_indexer_tester_sources() -> Any:
        """
        List all crawl sources that have a pages/ directory with markdown files for Indexer Tester.
        """
        try:
            sources_dir = _get_crawler_sources_dir()
            if not os.path.isdir(sources_dir):
                return jsonify({"sources": []})

            result: list[dict[str, Any]] = []
            for item in os.listdir(sources_dir):
                source_path = os.path.join(sources_dir, item)
                if not os.path.isdir(source_path):
                    continue
                pages_dir = os.path.join(source_path, "pages")
                if not os.path.isdir(pages_dir):
                    continue
                try:
                    files = [
                        name
                        for name in os.listdir(pages_dir)
                        if os.path.isfile(os.path.join(pages_dir, name))
                        and name.lower().endswith(".md")
                    ]
                except Exception:
                    files = []
                result.append(
                    {
                        "id": item,
                        "page_count": len(files),
                    }
                )

            result.sort(key=lambda x: x["id"])
            return jsonify({"sources": result})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_sources", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/sources/<source_id>/files", methods=["GET"])
    def get_indexer_tester_files(source_id: str) -> Any:
        """
        List markdown files for a specific source, with optional sorting by name or size.
        """
        try:
            sources_dir = _get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)

            sort_by = request.args.get("sort", "name")
            order = request.args.get("order", "asc")
            if sort_by not in ("name", "size"):
                sort_by = "name"
            if order not in ("asc", "desc"):
                order = "asc"

            files: list[dict[str, Any]] = []
            for name in os.listdir(pages_dir):
                if not name.lower().endswith(".md"):
                    continue
                full_path = os.path.join(pages_dir, name)
                if not os.path.isfile(full_path):
                    continue
                try:
                    size_bytes = os.path.getsize(full_path)
                except OSError:
                    size_bytes = 0
                files.append(
                    {
                        "filename": name,
                        "size_bytes": size_bytes,
                    }
                )

            reverse = order == "desc"
            if sort_by == "size":
                files.sort(key=lambda x: x["size_bytes"], reverse=reverse)
            else:
                files.sort(key=lambda x: x["filename"].lower(), reverse=reverse)

            return jsonify(
                {
                    "source_id": source_id,
                    "files": files,
                    "total": len(files),
                }
            )
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_files", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/sources/<source_id>/files/<path:filename>", methods=["GET"])
    def get_indexer_tester_file_detail(source_id: str, filename: str) -> Any:
        """
        Return original and processed markdown for a specific page using the WebUI backend pipeline.
        """
        try:
            sources_dir = _get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)

            # Normalize and validate path to stay under pages_dir
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                return _error_response("Invalid filename", 400)
            basename = os.path.basename(requested_path)
            if not basename.lower().endswith(".md"):
                return _error_response("Only .md files are supported", 400)
            if not os.path.isfile(requested_path):
                return _error_response("File not found", 404)

            meta = _load_source_meta(source_id) or {}
            page_entry = (meta.get("pages") or {}).get(basename, {})

            with open(requested_path, "r", encoding="utf-8") as f:
                source_md = f.read()

            pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
            if run_pipeline is None:
                return _error_response("md_indexer module not available", 500)
            page_meta, processed_md = run_pipeline(pipeline_name, source_md)

            return jsonify(
                {
                    "source_id": source_id,
                    "filename": basename,
                    "page_meta": page_meta or page_entry or {},
                    "source_md": source_md,
                    "processed_md": processed_md,
                }
            )
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_file_detail", exc_info=True)
            return _error_response(e)


    INDEXER_EVALUATE_SYSTEM_PROMPT_MAIN = """You are an expert on document processing for RAG. The user will provide PARSED METADATA (when available), then ORIGINAL markdown, PROCESSED markdown (after cleanup), and REMOVED CONTENT (the exact text that was deleted). Use REMOVED CONTENT to know precisely what was removed—do not guess from comparing ORIGINAL and PROCESSED.

    **Value rules (follow strictly):**
    - **Keep:** code examples, API signatures, configuration steps, migration notes, platform availability.
    - **Trim:** UI navigation text, empty headings, repeated descriptions, boilerplate sentences.
    - **Token efficiency:** Prefer keeping code examples and removing explanatory prose when both express the same concept. For developer RAG this works best.
    - If PROCESSED already contains a code example that demonstrates a concept, recommend removing explanatory paragraphs that only repeat what the code shows (common in Apple docs).
    - **Meta block:** Meta information is already preserved in metadata (see PARSED METADATA). The pipeline parses the meta comment into metadata and removes the comment from the text. Do not recommend restoring the meta comment block in the text. Do not suggest rules that target the comment syntax (e.g. delete_lines_exact with "<!--" or "-->"); that would break normal markdown.
    - **Code + explanation:** Keep at least one explanatory sentence for each code example. Do not recommend deleting all explanation and leaving only code; short explanations improve semantic retrieval.
    - **Inheritance / relationship sections:** Keep inheritance sections only if they contain concrete type names. Remove empty relationship sections (e.g. "Inherits From" with no content or only placeholder).
    - **Pipeline suggestions:** Do not suggest steps that contradict your analysis. Prefer structural rules (headings, UI text, boilerplate, section names). Avoid rules that target generic syntax tokens (e.g. "<!--", "-->", "```"); prefer rules tied to documentation structure. Avoid content-specific rules tied to a single document; such rules would break other documents.

    **Language:** Use the same language as the document. Do not translate quoted text.

    Answer in two sections with short bullet points. Be concrete: cite exact headings, phrases, or locations.

    **1. What in the PROCESSED text can still be trimmed:**
    - Apply the Trim rules above. List only concrete items: UI nav text, empty headings, repeated descriptions, boilerplate, or prose that duplicates code already in PROCESSED. One line per item; add a short quote or location if helpful.

    **2. What in REMOVED CONTENT was useful and should be kept:**
    - Look only at the REMOVED CONTENT block. List items that match the Keep rules (code, API signatures, config steps, migration notes, availability) and should be preserved by adjusting the pipeline. Do not list things that are still present in PROCESSED. Be specific so the pipeline can be adjusted."""

    INDEXER_EVALUATE_PIPELINE_STEPS_REF = """
    **Available pipeline step types** (you can suggest adding these to reduce noise or preserve useful content):

    - **strip_meta_block**: Remove leading <!-- meta ... --> HTML comment; parse meta (url, framework, etc.). No params.
    - **delete_lines_exact**: Remove lines that exactly match one of the given strings (e.g. "View in English", "Table of Contents"). Params: `lines` (list of strings), optional `case_sensitive` (bool).
    - **delete_lines_containing**: Remove lines that contain any of the given substrings (e.g. for "[View in English](url)" use substrings ["view in english"]). Params: `substrings` (list of strings), optional `case_sensitive` (bool).
    - **delete_lines_regex**: Remove each line that matches the regex. Params: `pattern` (string).
    - **delete_sentences_starting_with**: Remove whole prose sentences whose trimmed text starts with one of the prefixes, ignoring upper/lower case. Params: `prefixes` (list of strings).
    - **delete_range_regex**: Remove a range from first match of start_regex to first match of end_regex (or end of doc). Params: `start_regex`, optional `end_regex`.
    - **delete_regex_match**: Remove all non-overlapping matches of one regex (can be multiline). Params: `pattern` (string).
    - **strip_sections_by_heading**: Remove whole sections whose heading equals or starts with one of the list (e.g. "conforming types", "inherited by"). Params: `headings` (list of strings, lower case).
    - **normalize_whitespace**: Trim trailing space per line, collapse multiple spaces. No params.
    - **replace_regex**: Replace each match of pattern with replacement. Params: `pattern`, `replacement`.
    - **reject_low_signal_body**: After other steps, clear the body if it is too weak for RAG. Params: `min_chars` (e.g. 200), `min_words` (e.g. 5; use 0 to disable), `min_alpha_ratio` (0–1, e.g. 0.12; use 0 to disable). Place near the end of the pipeline.
    """

    INDEXER_EVALUATE_SYSTEM_PROMPT_SUGGEST = """
    **3. Suggested pipeline steps to add (required):**
    Always include section 3. Add a section "**3. Suggested pipeline steps to add:**". Based on sections 1 and 2, suggest one or more concrete pipeline steps that would improve this document's processing. For each suggestion give: step type (from the list above), and if the step has parameters, suggest concrete values (e.g. for delete_lines_exact suggest exact `lines: ["Advertisement", "Sign up"]`; for strip_sections_by_heading suggest `headings: ["see also"]`). If no steps would clearly help, write "None." Do not suggest steps that contradict your analysis. Do not suggest delete_lines_exact or delete_lines_containing with generic syntax like "<!--", "-->", or "```"—that would break markdown. Prefer structural rules (headings, UI text, boilerplate); avoid content-specific rules tied to a single document. Do not add a generic closing paragraph; end with the last suggested step or "None."
    """


    def _get_indexer_evaluate_system_prompt() -> str:
        return (
            INDEXER_EVALUATE_SYSTEM_PROMPT_MAIN
            + INDEXER_EVALUATE_PIPELINE_STEPS_REF
            + INDEXER_EVALUATE_SYSTEM_PROMPT_SUGGEST
        )


    # Sized for ~32k context: system + ORIGINAL + PROCESSED + REMOVED + response
    MAX_EVALUATE_CHARS = 40_000   # PROCESSED: ~10k tokens
    ORIGINAL_MAX_CHARS = 40_000   # ORIGINAL: ~10k tokens
    REMOVED_MAX_CHARS = 24_000    # REMOVED: ~6k tokens (~26k total for content, ~6k for system + reply)
    BATCH_EVAL_MIN_SIZE_BYTES = 1100  # 1.1 KB
    BATCH_EVAL_MIN_CHARS_AFTER_CLEANUP = 200  # after pipeline cleanup

    _batch_eval_jobs: dict[str, dict[str, Any]] = {}
    _batch_eval_lock = threading.Lock()


    def _compute_removed_content(original: str, processed: str, max_chars: int = 6_000) -> str:
        """Compute explicit diff: lines that were in original but removed (not in processed)."""
        if not original.strip():
            return "(empty original)"
        orig_lines = original.splitlines()
        proc_lines = processed.splitlines()
        matcher = difflib.SequenceMatcher(None, orig_lines, proc_lines)
        removed_lines = []
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag in ("delete", "replace"):
                removed_lines.extend(orig_lines[i1:i2])
        if not removed_lines:
            return "(nothing removed)"
        text = "\n".join(removed_lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[... truncated]"
        return text


    def _truncate_evaluate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n[... truncated]"


    PARSED_METADATA_KEY_ORDER = ("url", "framework", "availability", "doc_kind", "doc_scope", "doc_type")


    def _format_parsed_metadata(parsed_metadata: dict[str, Any]) -> str:
        """Format parsed metadata (e.g. from strip_meta_block) for the evaluation prompt. Key order: url, framework, availability, doc_kind, then rest."""
        if not parsed_metadata:
            return "(none)"
        lines = []
        seen = set()
        for k in PARSED_METADATA_KEY_ORDER:
            if k not in parsed_metadata:
                continue
            v = parsed_metadata[k]
            if v is None or v == "":
                continue
            if isinstance(v, (list, dict)):
                v = str(v)
            lines.append(f"{k}: {v}")
            seen.add(k)
        for k, v in sorted(parsed_metadata.items()):
            if k in seen:
                continue
            if v is None or v == "":
                continue
            if isinstance(v, (list, dict)):
                v = str(v)
            lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else "(none)"


    def _run_one_indexer_evaluate(
        source_md: str,
        processed_md: str,
        provider_id: str | None,
        model: str | None,
        chat_client: Any,
        params: Any,
        parsed_metadata: dict[str, Any] | None = None,
        original_max_chars: int | None = None,
        processed_max_chars: int | None = None,
        removed_max_chars: int | None = None,
    ) -> str:
        """Run a single LLM evaluation; returns reply text. Uses same prompts as indexer_tester_evaluate."""
        orig_max = original_max_chars if original_max_chars is not None else ORIGINAL_MAX_CHARS
        proc_max = processed_max_chars if processed_max_chars is not None else MAX_EVALUATE_CHARS
        rem_max = removed_max_chars if removed_max_chars is not None else REMOVED_MAX_CHARS
        source_md = _truncate_evaluate(source_md, orig_max)
        processed_md = _truncate_evaluate(processed_md, proc_max)
        removed_content = _compute_removed_content(
            source_md, processed_md, max_chars=rem_max
        )
        # Put PARSED METADATA first so the model sees that meta is already preserved before reading documents
        if parsed_metadata is not None:
            user_content = (
                "### PARSED METADATA\n\n"
                + _format_parsed_metadata(parsed_metadata)
                + "\n\n### ORIGINAL\n\n"
                + source_md
                + "\n\n### PROCESSED\n\n"
                + processed_md
                + "\n\n### REMOVED CONTENT\n\n"
                + removed_content
            )
        else:
            user_content = (
                "### ORIGINAL\n\n"
                + source_md
                + "\n\n### PROCESSED\n\n"
                + processed_md
                + "\n\n### REMOVED CONTENT\n\n"
                + removed_content
            )
        use_model = model if model else params.model_name
        if not use_model:
            raise ValueError("No chat model configured")
        system_prompt = _get_indexer_evaluate_system_prompt()
        provider_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options = {"temperature": 0.0}
        resolved_provider_id = str(provider_id or "").strip()
        if resolved_provider_id:
            return _invoke_runtime_chat(
                provider_id=resolved_provider_id,
                model=use_model,
                messages=provider_messages,
                options=options,
            )
        return chat_client.chat(provider_messages, use_model, stream=False, options=options) or ""


    def _batch_eval_worker(
        job_id: str,
        source_id: str,
        provider_id: str | None,
        model: str | None,
        count: int,
    ) -> None:
        sources_dir = _get_crawler_sources_dir()
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
            if not job or job["status"] != "running":
                return
        if not os.path.isdir(pages_dir):
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = "Source pages directory not found"
            return
        files: list[dict[str, Any]] = []
        for name in os.listdir(pages_dir):
            if not name.lower().endswith(".md"):
                continue
            full_path = os.path.join(pages_dir, name)
            if not os.path.isfile(full_path):
                continue
            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                size_bytes = 0
            if size_bytes < BATCH_EVAL_MIN_SIZE_BYTES:
                continue
            files.append({"filename": name, "size_bytes": size_bytes})
        # Keep only files that after pipeline cleanup have more than 200 characters
        if run_pipeline:
            pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
            filtered: list[dict[str, Any]] = []
            for entry in files:
                full_path = os.path.join(pages_dir, entry["filename"])
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        source_md = f.read()
                except Exception:
                    continue
                try:
                    _pm, processed_md = run_pipeline(pipeline_name, source_md)
                except Exception:
                    continue
                if len((processed_md or "").strip()) > BATCH_EVAL_MIN_CHARS_AFTER_CLEANUP:
                    filtered.append(entry)
            files = filtered
        random.shuffle(files)
        files = files[:count]
        total = len(files)
        with _batch_eval_lock:
            if job_id not in _batch_eval_jobs:
                return
            _batch_eval_jobs[job_id]["total"] = total
            _batch_eval_jobs[job_id]["results"] = []

        webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
        collection_name = (_get_qdrant_collection_names() or [None])[0]
        try:
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
        except Exception as e:
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = str(e)
            return
        chat_client = deps.chat_client
        use_model = model if model else (params.model_name if params else None)
        if not use_model:
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = "No chat model configured"
            return

        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
        eval_orig_max = job.get("original_max_chars") if job else None
        eval_proc_max = job.get("processed_max_chars") if job else None
        eval_rem_max = job.get("removed_max_chars") if job else None

        for i, entry in enumerate(files):
            with _batch_eval_lock:
                if job_id not in _batch_eval_jobs or _batch_eval_jobs[job_id]["status"] != "running":
                    return
                _batch_eval_jobs[job_id]["current_file"] = entry["filename"]
            filename = entry["filename"]
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                reply = "(invalid path)"
            else:
                try:
                    with open(requested_path, "r", encoding="utf-8") as f:
                        source_md = f.read()
                except Exception as e:
                    reply = f"(read error: {e})"
                else:
                    pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
                    if run_pipeline:
                        try:
                            _pm, processed_md = run_pipeline(pipeline_name, source_md)
                        except Exception as e:
                            reply = f"(pipeline error: {e})"
                        else:
                            try:
                                reply = _run_one_indexer_evaluate(
                                    source_md,
                                    processed_md,
                                    provider_id,
                                    model,
                                    chat_client,
                                    params,
                                    parsed_metadata=_pm,
                                    original_max_chars=eval_orig_max,
                                    processed_max_chars=eval_proc_max,
                                    removed_max_chars=eval_rem_max,
                                )
                                if not (reply or "").strip():
                                    reply = "(empty response from model)"
                            except Exception as e:
                                reply = f"(LLM error: {e})"
                    else:
                        reply = "(pipeline not available)"
            with _batch_eval_lock:
                if job_id not in _batch_eval_jobs:
                    return
                _batch_eval_jobs[job_id]["done"] = i + 1
                _batch_eval_jobs[job_id]["results"].append({"filename": filename, "reply": reply})

        with _batch_eval_lock:
            if job_id in _batch_eval_jobs:
                _batch_eval_jobs[job_id]["status"] = "done"
                _batch_eval_jobs[job_id]["current_file"] = None


    @bp.route("/crawler/indexer-tester/evaluate", methods=["POST"])
    @bp.route("/crawler/indexer-tester/evaluate/", methods=["POST"])
    def indexer_tester_evaluate() -> Any:
        """
        Send original and processed markdown to the local LLM for pipeline evaluation.
        No RAG; single turn. Returns { "reply": content } or { "error": "..." }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_md = body.get("source_md") or ""
            processed_md = body.get("processed_md") or ""
            provider_id = (body.get("provider_id") or "").strip() or None
            model = (body.get("model") or "").strip() or None
            page_meta = body.get("page_meta") if isinstance(body.get("page_meta"), dict) else None
            try:
                orig_max = int(body.get("original_max_chars")) if body.get("original_max_chars") is not None else None
                proc_max = int(body.get("processed_max_chars")) if body.get("processed_max_chars") is not None else None
                rem_max = int(body.get("removed_max_chars")) if body.get("removed_max_chars") is not None else None
                if orig_max is not None and (orig_max < 1000 or orig_max > 500_000):
                    orig_max = None
                if proc_max is not None and (proc_max < 1000 or proc_max > 500_000):
                    proc_max = None
                if rem_max is not None and (rem_max < 1000 or rem_max > 500_000):
                    rem_max = None
            except (TypeError, ValueError):
                orig_max = proc_max = rem_max = None

            if not source_md and not processed_md:
                return _error_response("At least one of source_md or processed_md is required", 400)

            webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
            collection_name = None
            names = _get_qdrant_collection_names()
            if names:
                collection_name = names[0]
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
            chat_client = deps.chat_client
            content = _run_one_indexer_evaluate(
                source_md,
                processed_md,
                provider_id,
                model,
                chat_client,
                params,
                parsed_metadata=page_meta,
                original_max_chars=orig_max,
                processed_max_chars=proc_max,
                removed_max_chars=rem_max,
            )
            return jsonify({"reply": content or ""})
        except ValueError as e:
            return _error_response(e, 400)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.indexer_tester_evaluate", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/evaluate-batch", methods=["POST"])
    def start_indexer_tester_evaluate_batch() -> Any:
        """Start a batch LLM evaluation job. Body: { source_id, model?, count }. Returns job_id."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_id = (body.get("source_id") or "").strip()
            provider_id = (body.get("provider_id") or "").strip() or None
            count = body.get("count")
            model = (body.get("model") or "").strip() or None
            if not source_id:
                return _error_response("source_id is required", 400)
            try:
                count = int(count) if count is not None else 0
            except (TypeError, ValueError):
                count = 0
            if count < 1 or count > 500:
                return _error_response("count must be between 1 and 500", 400)

            def _parse_limit(val: Any, default: int, min_val: int = 1000, max_val: int = 500_000) -> int:
                if val is None:
                    return default
                try:
                    n = int(val)
                    return max(min_val, min(max_val, n))
                except (TypeError, ValueError):
                    return default

            original_max = _parse_limit(body.get("original_max_chars"), ORIGINAL_MAX_CHARS)
            processed_max = _parse_limit(body.get("processed_max_chars"), MAX_EVALUATE_CHARS)
            removed_max = _parse_limit(body.get("removed_max_chars"), REMOVED_MAX_CHARS)

            job_id = str(uuid.uuid4())
            with _batch_eval_lock:
                _batch_eval_jobs[job_id] = {
                    "status": "running",
                    "total": 0,
                    "done": 0,
                    "current_file": None,
                    "results": [],
                    "error": None,
                    "source_id": source_id,
                    "original_max_chars": original_max,
                    "processed_max_chars": processed_max,
                    "removed_max_chars": removed_max,
                }
            thread = threading.Thread(
                target=_batch_eval_worker,
                args=(job_id, source_id, provider_id, model, count),
                daemon=True,
            )
            thread.start()
            return jsonify({"job_id": job_id})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.start_indexer_tester_evaluate_batch", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/evaluate-batch/status/<job_id>", methods=["GET"])
    def get_indexer_tester_evaluate_batch_status(job_id: str) -> Any:
        """Return batch job state: status, total, done, current_file, results, error."""
        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
        if not job:
            return _error_response("Job not found", 404)
        return jsonify({
            "job_id": job_id,
            "status": job["status"],
            "total": job["total"],
            "done": job["done"],
            "current_file": job.get("current_file"),
            "results": job.get("results") or [],
            "error": job.get("error"),
            "source_id": job.get("source_id"),
        })


    BATCH_PATTERNS_SYSTEM_PROMPT = """You are an expert on document processing for RAG. The user will provide a set of per-document evaluation replies from a batch run. Your task is to find **common patterns** across many documents and suggest **pipeline steps** that would improve processing for multiple documents at once.

    Rules:
    - Prefer structural rules (headings, UI text, boilerplate) that apply across docs.
    - Avoid content-specific rules tied to a single document (e.g. a phrase that appears in one file only).
    - Suggest concrete pipeline step types and parameters (e.g. strip_sections_by_heading with headings: ["see also", "relationships"]).
    - If you see the same recommendation in many replies (e.g. "empty ## Relationships section" in 40 docs), that is a strong candidate for one pipeline step.
    - Output: a short "Pattern" summary and "Suggested pipeline steps" with concrete steps. Be concise."""


    @bp.route("/crawler/indexer-tester/evaluate-batch/detect-patterns", methods=["POST"])
    def detect_batch_eval_patterns() -> Any:
        """
        Analyze batch evaluation results and return cross-document patterns and suggested pipeline steps.
        Body: { results: [{ filename, reply }, ...], model?: string }.
        Returns { patterns: "..." } or { error: "..." }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            results = body.get("results") or []
            provider_id = (body.get("provider_id") or "").strip() or None
            model = (body.get("model") or "").strip() or None
            if not results or not isinstance(results, list):
                return _error_response("results array is required", 400)

            # Build content: one block per doc (filename + first N chars of reply) to stay within context
            max_reply_chars = 600
            max_docs = 80
            parts = []
            for i, item in enumerate(results[:max_docs]):
                if not isinstance(item, dict):
                    continue
                fn = item.get("filename") or f"doc_{i}"
                reply = (item.get("reply") or "").strip()
                if len(reply) > max_reply_chars:
                    reply = reply[:max_reply_chars] + "\n[...]"
                parts.append(f"--- {fn} ---\n{reply}")
            if not parts:
                return _error_response("No valid results to analyze", 400)
            user_content = (
                "Below are per-document evaluation replies from a batch of "
                + str(len(results))
                + " files. Identify common patterns and suggest pipeline steps that would help many documents.\n\n"
                + "\n\n".join(parts)
            )

            webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
            collection_name = (_get_qdrant_collection_names() or [None])[0]
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
            chat_client = deps.chat_client
            use_model = model or (params.model_name if params else None)
            if not use_model:
                return _error_response("No chat model configured", 400)

            system_prompt = BATCH_PATTERNS_SYSTEM_PROMPT
            provider_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            options = {"temperature": 0.0}
            if provider_id:
                patterns = _invoke_runtime_chat(
                    provider_id=provider_id,
                    model=use_model,
                    messages=provider_messages,
                    options=options,
                )
            else:
                patterns = chat_client.chat(provider_messages, use_model, stream=False, options=options) or ""
            return jsonify({"patterns": (patterns or "").strip()})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.detect_batch_eval_patterns", exc_info=True)
            return _error_response(e)


    # ---- MD Pipelines (config-driven markdown cleanup) ----

    @bp.route("/crawler/md-pipelines", methods=["GET"])
    def get_md_pipelines_list() -> Any:
        """List available pipeline names (config/md_pipelines/*.json)."""
        if list_pipeline_names is None:
            return _error_response("md_indexer module not available", 500)
        try:
            names = list_pipeline_names()
            return jsonify({"pipelines": names})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_md_pipelines_list", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["GET"])
    def get_md_pipeline(name: str) -> Any:
        """Get pipeline JSON by name."""
        if load_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            pipeline = load_pipeline(name)
            if pipeline is None:
                return _error_response(f"Pipeline '{name}' not found", 404)
            return jsonify(pipeline.to_dict())
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["PUT", "POST"])
    def save_md_pipeline(name: str) -> Any:
        """Save pipeline JSON by name. Body: { "name": "...", "steps": [...] }."""
        if save_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            body = request.get_json(force=True, silent=True) or {}
            if "steps" not in body:
                return _error_response("Missing 'steps' in body", 400)
            from modules.md_indexer.domain.schema import Pipeline
            pipeline = Pipeline.from_dict(body)
            save_pipeline(name, pipeline)
            return jsonify({"ok": True, "name": name})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.save_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["DELETE"])
    def delete_md_pipeline(name: str) -> Any:
        """Delete pipeline by name."""
        if md_indexer_delete_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            if md_indexer_delete_pipeline(name):
                return jsonify({"ok": True, "name": name})
            return _error_response(f"Pipeline '{name}' not found", 404)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.delete_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/preview", methods=["POST"])
    def preview_md_pipeline() -> Any:
        """Run a pipeline on a source file and return source_md + processed_md."""
        if run_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            body = request.get_json(force=True, silent=True) or {}
            pipeline_name = body.get("pipeline_name")
            pipeline_definition = body.get("pipeline")
            source_id = body.get("source_id")
            filename = body.get("filename")
            if not source_id or not filename:
                return _error_response("Missing source_id or filename", 400)
            sources_dir = _get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                return _error_response("Invalid filename", 400)
            basename = os.path.basename(requested_path)
            if not basename.lower().endswith(".md"):
                return _error_response("Only .md files are supported", 400)
            if not os.path.isfile(requested_path):
                return _error_response("File not found", 404)
            with open(requested_path, "r", encoding="utf-8") as f:
                source_md = f.read()
            pipeline_to_run = pipeline_definition if isinstance(pipeline_definition, dict) else pipeline_name
            if pipeline_to_run is None and get_active_pipeline_name is not None:
                pipeline_to_run = get_active_pipeline_name()
            page_meta, processed_md = run_pipeline(pipeline_to_run, source_md)
            return jsonify({
                "source_id": source_id,
                "filename": basename,
                "page_meta": page_meta,
                "source_md": source_md,
                "processed_md": processed_md,
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.preview_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>/stats", methods=["GET"])
    def get_crawler_source_stats(source_id: str) -> Any:
        """Get statistics for a source."""
        try:
            meta = _load_source_meta(source_id)
            if not meta:
                return _error_response("Source not found", 404)
        
            stats = _get_source_stats(meta)
            return jsonify({
                "source_id": source_id,
                **stats,
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source_stats", exc_info=True)
            return _error_response(e)


    # Track crawling processes
    _crawling_processes: dict[str, subprocess.Popen] = {}


    @bp.route("/crawler/sources/<source_id>/crawl", methods=["POST"])
    def crawl_source_endpoint(source_id: str) -> Any:
        """Start crawling a specific source. Returns immediately, crawl runs in background."""
        try:
            # Check if source exists
            meta = _load_source_meta(source_id)
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
        
            # Run crawl in subprocess
            env = os.environ.copy()
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
                except Exception:
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


    def _load_sources_config() -> list[dict]:
        """Load sources from config/sources.yaml."""
        try:
            import yaml
        
            config_path = os.path.join(_ROOT, "config", "sources.yaml")
            if not os.path.isfile(config_path):
                return []
        
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        
            return data.get("sources", [])
        except Exception as e:
            _WEBUI_LOG.warning(f"Failed to load sources config: {e}")
            return []


    def _save_sources_config(sources: list[dict]) -> bool:
        """Save sources to config/sources.yaml. Returns True on success."""
        try:
            import yaml
        
            config_path = os.path.join(_ROOT, "config", "sources.yaml")
            config_dir = os.path.dirname(config_path)
            os.makedirs(config_dir, exist_ok=True)
        
            data = {"sources": sources}
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
            return True
        except Exception as e:
            _WEBUI_LOG.error(f"Failed to save sources config: {e}")
            return False


    def _run_create_collection_job(
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
                stats = _create_collection_from_sources(
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
                    except Exception:
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
                _touch_collection_job_timing(job)
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
            except Exception:
                pass

            available_sources = []
            for source_id in source_ids:
                meta = _load_source_meta(source_id)
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
            total_pages = 0
            for sid in available_sources:
                meta = _load_source_meta(sid)
                if meta and meta.get("pages"):
                    total_pages += len(meta.get("pages", {}))

            with _collection_jobs_lock:
                started_perf = time.perf_counter()
                _collection_jobs[job_id] = {
                    "status": "running",
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
                target=_run_create_collection_job,
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
                "status": "started",
                "collection_name": collection_name,
            }), 202

        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.create_collection", exc_info=True)
            return _error_response(e)

    register_crawler_source_routes(
        bp,
        error_log=error_log,
        get_crawler_sources_dir=lambda: _get_crawler_sources_dir(),
        load_source_meta=lambda source_id: _load_source_meta(source_id),
        load_sources_config=lambda: _load_sources_config(),
        save_sources_config=lambda sources: _save_sources_config(sources),
    )


__all__ = ["register_crawler_routes"]
