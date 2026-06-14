"""Indexing helpers used by crawler collection routes."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from config import get_indexing_int
from infrastructure.database import get_logs_repository

_WEBUI_LOG = logging.getLogger("webui")
_DEFAULT_MAX_EMBED_CHARS = 1_800
_INDEXING_EMBED_PATH_LOGGED = False


def import_qdrant() -> tuple[type, type, type, type, type, type]:
    """Lazy-load qdrant_client types used by collection indexing."""
    from qdrant_client import QdrantClient as _QC  # noqa: PLC0415
    from qdrant_client.http.models import (  # noqa: PLC0415
        Distance as _Dist,
        PayloadSchemaType as _PST,
        PointStruct as _PS,
        SparseVectorParams as _SVP,
        VectorParams as _VP,
    )

    return _QC, _Dist, _PST, _PS, _SVP, _VP


def create_collection_log_metadata(
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


def write_create_collection_final_log(
    *,
    job_id: str,
    collection_name: str,
    source_ids: list[str],
    status: str,
    stats: dict[str, Any],
    error: str = "",
) -> None:
    metadata = create_collection_log_metadata(
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


def config_default_embed_model() -> str:
    try:
        from config import get_default_embed_model

        return str(get_default_embed_model() or "").strip()
    except Exception:
        return os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")


def max_embed_chars() -> int:
    return max(256, get_indexing_int("embed_truncate_chars", _DEFAULT_MAX_EMBED_CHARS))


def clip_text_for_embedding(text: str, max_chars: int | None = None) -> str:
    """Clip embed input at a readable boundary before provider context checks."""
    value = text or ""
    limit = max_chars if max_chars is not None else max_embed_chars()
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


def is_embed_context_length_error(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return "context length" in text or "input length exceeds" in text


def runtime_embed_available() -> bool:
    """True when Flask app has extension runtime or llm_proxy wiring (not plain webui_backend.app)."""
    try:
        from flask import current_app, has_app_context

        if not has_app_context():
            return False
        if current_app.extensions.get("llm_proxy_wiring") is not None:
            return True
        from api.http.extensions_service_access import get_extensions_runtime

        return get_extensions_runtime(current_app) is not None
    except Exception:
        return False


def log_indexing_embed_path_once(path: str) -> None:
    global _INDEXING_EMBED_PATH_LOGGED
    if _INDEXING_EMBED_PATH_LOGGED:
        return
    _INDEXING_EMBED_PATH_LOGGED = True
    _WEBUI_LOG.info("Create-collection embedding path: %s", path)
