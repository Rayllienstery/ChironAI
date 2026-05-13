"""
Flask routes for WebUI frontend.

Exposes /api/webui/* endpoints for models, prompts, logs, chat, and config.
Provides enhanced chat endpoint with RAG metadata and in-memory request buffer for dev console.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import random
import sys
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from core.contracts.webui_api import WEBUI_URL_PREFIX

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# rag_service + chironai_rag live under CoreModules/RagService (see chironai-rag-service pyproject).
# External docs RAG (on-demand fetch, GitHub discovery).
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)
# CoreModules/WebInteraction (web_interaction package).
_WEBINTERACTION = os.path.join(_ROOT, "CoreModules", "WebInteraction")
if _WEBINTERACTION not in sys.path:
    sys.path.insert(0, _WEBINTERACTION)
# CoreModules/MdIngestionService (md_ingestion_service package).
_MD_INGESTION = os.path.join(_ROOT, "CoreModules", "MdIngestionService")
if _MD_INGESTION not in sys.path:
    sys.path.insert(0, _MD_INGESTION)
_RAG_SVC = os.path.join(_ROOT, "CoreModules", "RagService")
if os.path.isdir(_RAG_SVC) and _RAG_SVC not in sys.path:
    sys.path.insert(0, _RAG_SVC)
_LLM_PROXY = os.path.join(_ROOT, "CoreModules", "LlmProxy")
if os.path.isdir(_LLM_PROXY) and _LLM_PROXY not in sys.path:
    sys.path.insert(0, _LLM_PROXY)
_LLM_INTERACTOR = os.path.join(_ROOT, "CoreModules", "LlmInteractor")
if os.path.isdir(_LLM_INTERACTOR) and _LLM_INTERACTOR not in sys.path:
    sys.path.insert(0, _LLM_INTERACTOR)
_DOCKER_MANAGER = os.path.join(_ROOT, "CoreModules", "DockerManager")
if os.path.isdir(_DOCKER_MANAGER) and _DOCKER_MANAGER not in sys.path:
    sys.path.insert(0, _DOCKER_MANAGER)
_ERROR_MANAGER = os.path.join(_ROOT, "CoreModules", "ErrorManager")
if os.path.isdir(_ERROR_MANAGER) and _ERROR_MANAGER not in sys.path:
    sys.path.insert(0, _ERROR_MANAGER)

from error_manager.exceptions import ValidationError as _ValidationError
from error_manager.http import error_response as _error_response

from application.llm_proxy_builds import (
    LLM_PROXY_BUILDS_APP_KEY,
    diagnose_build,
    dump_builds_json,
    extract_context_length_from_show,
    find_build_by_id,
    load_builds_json,
    validate_builds_list,
)
from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_hybrid_sparse_enabled,
    resolve_web_interaction_flags,
)
from application.rag.params import get_rag_answer_params
from llm_proxy.api_key import (
    delete_proxy_api_key_record,
    generate_proxy_api_key_record,
    proxy_api_key_status,
    reveal_proxy_api_key,
    store_proxy_api_key_record,
)

try:
    from rag_service.infrastructure.keyword_collections_sqlite import get_keyword_collections_repository
except ImportError:
    get_keyword_collections_repository = None  # type: ignore[assignment]

try:
    from external_docs_rag.application.use_cases import (
        build_merged_rag_context,
        ingest_github_repo_markdown,
        resolve_rag_sources_for_request,
    )
    from external_docs_rag.config_loader import (
        load_external_sources,
        load_github_repos,
        load_rag_sources_config,
    )
    from external_docs_rag.infrastructure import (
        HttpFetchClient,
        QdrantChunkSink,
        QdrantRagSearchAdapter,
    )
    from external_docs_rag.infrastructure.github_discovery import get_latest_release_tag
    _EXTERNAL_DOCS_RAG_AVAILABLE = True
except ImportError:
    build_merged_rag_context = None  # type: ignore[assignment]
    resolve_rag_sources_for_request = None  # type: ignore[assignment]
    ingest_github_repo_markdown = None  # type: ignore[assignment]
    load_rag_sources_config = None  # type: ignore[assignment]
    load_external_sources = None  # type: ignore[assignment]
    load_github_repos = None  # type: ignore[assignment]
    HttpFetchClient = None  # type: ignore[assignment]
    QdrantChunkSink = None  # type: ignore[assignment]
    QdrantRagSearchAdapter = None  # type: ignore[assignment]
    get_latest_release_tag = None  # type: ignore[assignment]
    _EXTERNAL_DOCS_RAG_AVAILABLE = False

from config import (
    get_default_rag_top_k,
    get_framework_collection_ttl_days,
    get_qdrant_url,
    get_rag_float,
    get_rag_int,
    get_rag_prompt_name,
    get_retrieval_bool,
    get_retrieval_int,
    get_server_host,
    get_server_port,
)
from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from infrastructure.rag.qdrant_point_builder import build_named_vectors
from domain.services.rag_trigger import compute_rag_trigger_score
from config.rag_prompts import (
    get_rag_system_prompt,
    rag_prompt_file_exists,
    PROMPTS_DIR,
)

# Trash directory for deleted prompts
TRASH_DIR = PROMPTS_DIR / ".trash"
def _get_rag_required_keywords_from_module() -> list[str] | None:
    """Return flat list of enabled keywords from rag_service module, or None to use config default."""
    if get_keyword_collections_repository is None:
        return None
    try:
        repo = get_keyword_collections_repository()
        flat = repo.get_enabled_keywords_flat()
        return flat if flat else None
    except Exception:
        return None


def _get_effective_rag_trigger_threshold() -> int:
    """Return RAG trigger threshold: app_settings override or config default."""
    try:
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting("rag_trigger_threshold")
        if raw is not None and str(raw).strip() != "":
            return int(raw)
    except Exception:
        pass
    return get_retrieval_int("rag_trigger_threshold", 2)


# Static table for RAG trigger scoring (for UI)
RAG_TRIGGER_HELP_ROWS = [
    {"signal": "Keyword (from collections or config)", "points": "+3"},
    {"signal": "CamelCase (e.g. SwiftUI, URLSession)", "points": "+2"},
    {"signal": "Code block (```)", "points": "+4"},
    {"signal": "Code keyword (func, class, struct, let, var…)", "points": "+4"},
    {"signal": "API signature name(...)", "points": "+2"},
    {"signal": "File extension (.swift, .py…)", "points": "+2"},
    {"signal": "snake_case (e.g. load_data)", "points": "+1"},
    {"signal": "Strong technical phrase (error, API, framework…)", "points": "+2"},
    {"signal": "Weak technical phrase (how does, best practice…)", "points": "+1"},
]


from domain.services.prompt_builder import (
    build_system_content,
)
from llm_proxy.config import AUTOCOMPLETE_MODEL_ID

from chironai_rag.bindings import ConsumerRagBindings
from chironai_rag.consumers import RAG_COLLECTION_APP_SETTING, RagConsumer

from infrastructure.database import (
    get_session_manager,
    get_logs_repository,
    get_notifications_repository,
    get_settings_repository,
)
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from api.http.webui_crawler_helpers import is_safe_identifier
from api.http.webui_crawler_source_routes import register_crawler_source_routes
from api.http.webui_docker_routes import register_docker_routes
from api.http.webui_extensions_routes import register_extension_routes
from api.http.webui_prompt_routes import register_prompt_routes
from api.http.webui_prompts import is_readme_name
from api.http.webui_session import log_to_database
from api.http.proxy_status import (
    set_proxy_status,
    set_latest_request_seconds,
    get_proxy_status_label,
    get_latest_request_seconds,
    get_latest_request_total_tokens,
    get_latest_request_rag_steps,
    STATUS_IDLE,
)
from api.http.proxy_trace import (
    annotate_proxy_trace_for_ui,
    clear_proxy_trace_buffer,
    get_active_traces,
    get_current_trace,
    get_current_trace_updated_at,
    recent_proxy_traces,
)
from api.http.service_control import (
    start_qdrant as start_qdrant_service,
    stop_qdrant as stop_qdrant_service,
)

import requests

from infrastructure.ollama.cli_runner import (
    invoke_ping,
    invoke_tags,
)
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

# Import domain services for indexing
from domain.services.chunking import (
    chunk_quality_ok,
    split_markdown_into_chunks,
)
from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing
from domain.services.metadata_inference import (
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)

# MD indexer pipeline (config-driven markdown cleanup for RAG)
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

import hashlib
import subprocess

# In-memory buffer for dev console (last 50 requests)
_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

webui_bp = Blueprint("webui", __name__, url_prefix=WEBUI_URL_PREFIX)

register_prompt_routes(
    webui_bp,
    prompts_dir=PROMPTS_DIR,
    trash_dir=TRASH_DIR,
    error_log=_ERROR_LOG,
)
register_crawler_source_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    get_crawler_sources_dir=lambda: _get_crawler_sources_dir(),
    load_source_meta=lambda source_id: _load_source_meta(source_id),
    load_sources_config=lambda: _load_sources_config(),
    save_sources_config=lambda sources: _save_sources_config(sources),
)
register_extension_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
register_docker_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)


_SERVICE_STATUS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SERVICE_STATUS_CACHE_LOCK = threading.Lock()


def _get_cached_status(key: str, ttl_sec: float, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    now = time.time()
    with _SERVICE_STATUS_CACHE_LOCK:
        hit = _SERVICE_STATUS_CACHE.get(key)
        if hit is not None:
            ts, payload = hit
            if now - ts <= ttl_sec:
                return payload
    payload = compute()
    with _SERVICE_STATUS_CACHE_LOCK:
        _SERVICE_STATUS_CACHE[key] = (now, payload)
    return payload


_LAST_QDRANT_WARN_AT: float = 0.0


def _qdrant_status_snapshot(timeout_sec: float) -> dict[str, Any]:
    url = get_qdrant_url().rstrip("/")
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        resp = requests.get(f"{url}/collections", timeout=timeout_sec)
        status["http_status"] = resp.status_code
        if resp.ok:
            data = resp.json() or {}
            collections = data.get("result", {}).get("collections", [])
            status["running"] = True
            status["collections_count"] = len(collections)
            try:
                version_resp = requests.get(f"{url}/cluster", timeout=timeout_sec)
                if version_resp.ok:
                    vdata = version_resp.json() or {}
                    status["version"] = (
                        vdata.get("result", {})
                        .get("status", {})
                        .get("version")
                    )
            except Exception:
                pass
    except Exception as e:
        status["error"] = str(e)
        global _LAST_QDRANT_WARN_AT
        now = time.time()
        if now - _LAST_QDRANT_WARN_AT >= 30:
            _LAST_QDRANT_WARN_AT = now
            _WEBUI_LOG.warning("Failed to get Qdrant status: %s", e)
    return status


def _get_ollama_url() -> str:
    """Ollama HTTP base for WebUI (model list, ping): same origin as RAG/chat (config), not ServiceStarter port 11343."""
    try:
        from config import get_ollama_base_url

        return get_ollama_base_url().rstrip("/")
    except Exception:
        return (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")


def _legacy_default_chat_model() -> str:
    try:
        from config import get_ollama_chat_model

        return str(get_ollama_chat_model() or "").strip()
    except Exception:
        return ""


def _legacy_default_embed_model() -> str:
    try:
        from config import get_ollama_embed_model

        return str(get_ollama_embed_model() or "").strip()
    except Exception:
        return ""


def _legacy_default_rerank_model() -> str:
    try:
        from config import get_ollama_rerank_model

        return str(get_ollama_rerank_model() or "").strip()
    except Exception:
        return ""


def _legacy_embed_url() -> str:
    try:
        from config import get_ollama_embed_url

        return str(get_ollama_embed_url() or "").strip()
    except Exception:
        return "http://localhost:11434/api/embed"


def _run_unified_proxy_chat(body: dict[str, Any]) -> Any:
    """Delegate chat handling to /v1 chat_completions core to avoid duplicate RAG logic."""
    wiring = current_app.extensions.get("llm_proxy_wiring")
    if wiring is None:
        return _error_response("LLM proxy wiring not initialized", 500)
    from llm_proxy.chat_completions import run_chat_completions

    return run_chat_completions(wiring, body_override=body)



@webui_bp.route("/models", methods=["GET"])
def get_models() -> Any:
    """Return flattened chat-capable provider models for WebUI selectors."""
    try:
        catalog = _provider_catalog_payload(capability="chat")
        models_list: list[dict[str, Any]] = []
        for model in catalog.get("models") or []:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id") or "").strip()
            provider_id = str(model.get("provider_id") or "").strip()
            if not model_id:
                continue
            models_list.append(
                {
                    "id": model_id,
                    "name": model.get("label") or model_id,
                    "description": model.get("description") or f"{provider_id} model: {model_id}",
                    "provider_id": provider_id,
                    "provider_title": model.get("provider_title") or provider_id,
                    "size": (model.get("metadata") or {}).get("size", 0),
                    "modified_at": (model.get("metadata") or {}).get("modified_at", ""),
                }
            )
        if not models_list:
            model_name = _legacy_default_chat_model()
            models_list.append(
                {
                    "id": model_name,
                    "name": model_name,
                    "description": f"Default model: {model_name}",
                    "provider_id": _default_llm_provider_id(),
                    "provider_title": _default_llm_provider_id(),
                }
            )

        try:
            settings_repo = get_settings_repository()
            if (settings_repo.get_app_setting("proxy_autocomplete_model") or "").strip():
                models_list.insert(0, {
                    "id": AUTOCOMPLETE_MODEL_ID,
                    "name": AUTOCOMPLETE_MODEL_ID,
                    "description": "Autocomplete (maps to LLM Proxy → Autocomplete provider/model)",
                    "provider_id": str(settings_repo.get_app_setting("proxy_autocomplete_provider_id") or "").strip()
                    or _default_llm_provider_id(),
                })
        except Exception:
            pass

        return jsonify({"models": models_list})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_models", exc_info=True)
        log_to_database("ERROR", str(e), source="webui_routes.get_models", error_type=type(e).__name__)
        return _error_response(e)


@webui_bp.route("/config", methods=["GET"])
def get_config() -> Any:
    """Return current RAG configuration."""
    try:
        return jsonify({
            "context_chunk_chars": get_rag_int("context_chunk_chars", 1000),
            "context_total_chars": get_rag_int("context_total_chars", 7000),
            "top_k": get_rag_int("top_k", 4),
            "confidence_threshold": get_rag_float("confidence_threshold", 0.75),
            "model_name": _legacy_default_chat_model(),
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_config", exc_info=True)
        return _error_response(e)


@webui_bp.route("/sessions", methods=["GET"])
def get_sessions() -> Any:
    """Get or create a session."""
    try:
        session_id = request.args.get("session_id")
        session_manager = get_session_manager()
        session = session_manager.get_or_create_session(session_id)
        return jsonify(session)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_sessions", exc_info=True)
        return _error_response(e)


def _parse_since_id_query(raw: str | None) -> int | None:
    """Parse ``since_id`` query param; ``None`` if absent or empty. ``0`` is valid."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _log_webui_logs_read_duration(
    logs_repo: Any,
    *,
    endpoint: str,
    limit: int,
    since_id: int | None,
    duration_ms: float,
) -> None:
    """Append timing row to system logs. Skip fast incremental polls (anti-spam)."""
    try:
        incremental = since_id is not None
        if incremental and duration_ms < 250.0:
            return
        # Proxy list polls often omit since_id with a date window; avoid a row every few seconds.
        if not incremental and "proxy-logs" in endpoint and duration_ms < 250.0:
            return
        msg = (
            f"{endpoint} limit={limit} since_id={since_id if since_id is not None else 'none'} "
            f"duration_ms={duration_ms:.1f}"
        )
        logs_repo.add_log(
            "system",
            "INFO",
            msg,
            source="webui_api",
            error_type=None,
            metadata={
                "endpoint": endpoint,
                "limit": limit,
                "since_id": since_id,
                "duration_ms": round(duration_ms, 2),
            },
        )
    except Exception:
        pass


@webui_bp.route("/logs", methods=["GET"])
def get_logs() -> Any:
    """Return recent log entries from database."""
    try:
        session_id = request.args.get("session_id")
        limit = int(request.args.get("limit", 100))
        level = request.args.get("level", "").upper() or None
        source = request.args.get("source") or None
        since_id_val = _parse_since_id_query(request.args.get("since_id"))

        if not session_id:
            return _error_response("session_id is required", 400)

        logs_repo = get_logs_repository()
        t0 = time.perf_counter()
        logs = logs_repo.get_logs(
            session_id=session_id,
            level=level,
            limit=limit,
            since_id=since_id_val,
            source=source,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0
        _log_webui_logs_read_duration(
            logs_repo,
            endpoint="GET /api/webui/logs",
            limit=limit,
            since_id=since_id_val,
            duration_ms=duration_ms,
        )

        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_logs", exc_info=True)
        return _error_response(e)


@webui_bp.route("/notifications", methods=["GET"])
def get_coreui_notifications() -> Any:
    """List CoreUI notification center entries for a session."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return _error_response("session_id is required", 400)
        limit = min(500, max(1, int(request.args.get("limit", 200))))
        include_raw = (request.args.get("include_dismissed") or "true").strip().lower()
        include_dismissed = include_raw in ("1", "true", "yes")
        repo = get_notifications_repository()
        items = repo.list_notifications(
            session_id=session_id,
            limit=limit,
            include_dismissed=include_dismissed,
        )
        if session_id != "system":
            system_items = repo.list_notifications(
                session_id="system",
                limit=limit,
                include_dismissed=include_dismissed,
            )
            items.extend(system_items)
            items.sort(
                key=lambda n: (
                    str(n.get("last_occurrence_at") or n.get("created_at") or ""),
                    int(n.get("id") or 0),
                ),
                reverse=True,
            )
            items = items[:limit]
        return jsonify({"notifications": items})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_coreui_notifications", exc_info=True)
        return _error_response(e)


@webui_bp.route("/notifications", methods=["POST"])
def create_coreui_notification() -> Any:
    """Create a persisted notification (error or event)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        kind = (body.get("kind") or "event").strip().lower()
        source = (body.get("source") or "").strip()
        title = (body.get("title") or "").strip()
        message = body.get("message") or ""
        metadata = body.get("metadata")
        aggregation_key = (body.get("aggregation_key") or "").strip()

        if not session_id:
            return _error_response("session_id is required", 400)
        if kind not in ("error", "event", "info"):
            return _error_response("kind must be error, event, or info", 400)
        if not source:
            return _error_response("source is required", 400)
        if not title:
            return _error_response("title is required", 400)
        if not isinstance(message, str):
            message = str(message)
        if len(message) > 8000:
            message = message[:8000] + "…"
        meta_dict: dict[str, Any] | None = None
        if metadata is not None:
            if not isinstance(metadata, dict):
                return _error_response("metadata must be an object", 400)
            meta_dict = metadata
        if not aggregation_key:
            aggregation_key = None

        nid = get_notifications_repository().add_notification(
            session_id=session_id,
            kind=kind,
            source=source,
            title=title,
            message=message,
            metadata=meta_dict,
            aggregation_key=aggregation_key,
        )
        return jsonify({"id": nid})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.create_coreui_notification", exc_info=True)
        return _error_response(e)


@webui_bp.route("/notifications/<int:nid>/dismiss", methods=["PATCH"])
def dismiss_coreui_notification(nid: int) -> Any:
    """Mark a notification as dismissed."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id") or request.args.get("session_id")
        if not session_id:
            return _error_response("session_id is required", 400)
        repo = get_notifications_repository()
        ok = repo.dismiss(session_id, nid)
        if not ok and session_id != "system":
            ok = repo.dismiss("system", nid)
        if not ok:
            return _error_response("not found or already dismissed", 404)
        return jsonify({"ok": True})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.dismiss_coreui_notification", exc_info=True)
        return _error_response(e)


@webui_bp.route("/notifications/clear", methods=["POST"])
def clear_coreui_notifications() -> Any:
    """Remove all persisted notifications for the session (live activities unaffected)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        if not session_id:
            return _error_response("session_id is required", 400)
        deleted = get_notifications_repository().clear_session(session_id)
        return jsonify({"deleted": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.clear_coreui_notifications", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-logs", methods=["GET"])
def get_proxy_logs() -> Any:
    """Return proxy logs from database (``session_id=proxy``, ``source=proxy``).

    ``since_id`` (max id from the previous poll) and ``limit`` apply in insertion order.
    """
    try:
        limit = int(request.args.get("limit", 100))
        since_id_val = _parse_since_id_query(request.args.get("since_id"))
        from_date = request.args.get("from")
        to_date = request.args.get("to")
        ac_raw = (request.args.get("autocomplete_only") or "").strip().lower()
        autocomplete_only = ac_raw in ("1", "true", "yes")

        logs_repo = get_logs_repository()
        t0 = time.perf_counter()
        if autocomplete_only:
            logs = logs_repo.get_logs(
                session_id="proxy",
                level="INFO",
                limit=limit,
                since_id=since_id_val,
                source="proxy",
                from_date=from_date or None,
                to_date=to_date or None,
                autocomplete_only=True,
            )
        else:
            logs = logs_repo.get_logs(
                session_id="proxy",
                level="INFO",
                limit=limit,
                since_id=since_id_val,
                source="proxy",
                include_system=False,
                from_date=from_date or None,
                to_date=to_date or None,
            )
        duration_ms = (time.perf_counter() - t0) * 1000.0
        _log_webui_logs_read_duration(
            logs_repo,
            endpoint="GET /api/webui/proxy-logs",
            limit=limit,
            since_id=since_id_val,
            duration_ms=duration_ms,
        )

        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_logs", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-trace/current", methods=["GET"])
def get_proxy_trace_current() -> Any:
    """Return the latest live trace from in-memory store."""
    try:
        trace = get_current_trace()
        active_traces = get_active_traces()
        updated_at = get_current_trace_updated_at()
        return jsonify(
            {
                "trace": trace,
                "active_traces": active_traces,
                "status": get_proxy_status_label(),
                "updated_at": updated_at,
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_trace_current", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-traces", methods=["GET"])
def get_proxy_traces() -> Any:
    """Ring-buffer snapshots of LLM proxy traces (RAG Fusion Proxy → Traces), UI-oriented JSON."""
    try:
        lim_raw = request.args.get("limit", "40")
        limit = max(1, min(200, int(lim_raw)))
    except (TypeError, ValueError):
        limit = 40
    try:
        rows = list(reversed(recent_proxy_traces(limit)))
        traces = [
            annotate_proxy_trace_for_ui(r) if isinstance(r, dict) else r for r in rows
        ]
        return jsonify({"available": True, "traces": traces})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_traces", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-traces/clear", methods=["POST"])
def post_proxy_traces_clear() -> Any:
    try:
        clear_proxy_trace_buffer()
        return jsonify({"ok": True})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.post_proxy_traces_clear", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-journal", methods=["GET"])
def get_proxy_journal() -> Any:
    """Persisted proxy request rows only (session_id=proxy)."""
    try:
        lim_raw = request.args.get("limit", "200")
        limit = max(1, min(5000, int(lim_raw)))
    except (TypeError, ValueError):
        limit = 200
    since_id = request.args.get("since_id")
    from_date = (request.args.get("from") or "").strip() or None
    to_date = (request.args.get("to") or "").strip() or None
    try:
        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id="proxy",
            level="INFO",
            limit=limit,
            since_id=int(since_id) if since_id else None,
            source="proxy",
            include_system=False,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify({"ok": True, "logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_journal", exc_info=True)
        return jsonify({"ok": False, "logs": [], "error": str(e)}), 500


@webui_bp.route("/proxy-journal", methods=["DELETE"])
def delete_proxy_journal() -> Any:
    """Delete persisted proxy log rows (same scope as DELETE /proxy-logs without autocomplete filter)."""
    try:
        logs_repo = get_logs_repository()
        deleted = logs_repo.delete_proxy_logs(autocomplete_only=False)
        return jsonify({"ok": True, "deleted_count": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_proxy_journal", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@webui_bp.route("/logs", methods=["POST"])
def create_log() -> Any:
    """Create a log entry."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        level = body.get("level", "INFO").upper()
        message = body.get("message", "")
        source = body.get("source")
        error_type = body.get("error_type")
        metadata = body.get("metadata")
        
        if not session_id or not message:
            return _error_response("session_id and message are required", 400)
        
        logs_repo = get_logs_repository()
        log_id = logs_repo.add_log(
            session_id=session_id,
            level=level,
            message=message,
            source=source,
            error_type=error_type,
            metadata=metadata,
        )
        
        return jsonify({"id": log_id, "status": "created"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.create_log", exc_info=True)
        return _error_response(e)


@webui_bp.route("/logs", methods=["DELETE"])
def delete_logs() -> Any:
    """Delete log entries for a session from the database (matches GET scope by default)."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return _error_response("session_id is required", 400)
        inc_raw = (request.args.get("include_system") or "1").strip().lower()
        include_system = inc_raw not in ("0", "false", "no")

        logs_repo = get_logs_repository()
        deleted = logs_repo.delete_logs_for_session(
            session_id, include_system=include_system
        )
        return jsonify({"status": "ok", "deleted_count": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_logs", exc_info=True)
        return _error_response(e)


@webui_bp.route("/proxy-logs", methods=["DELETE"])
def delete_proxy_logs() -> Any:
    """Delete proxy (and optionally autocomplete-only) logs from the database."""
    try:
        ac_raw = (request.args.get("autocomplete_only") or "").strip().lower()
        autocomplete_only = ac_raw in ("1", "true", "yes")

        logs_repo = get_logs_repository()
        deleted = logs_repo.delete_proxy_logs(autocomplete_only=autocomplete_only)
        return jsonify({"status": "ok", "deleted_count": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_proxy_logs", exc_info=True)
        return _error_response(e)


@webui_bp.route("/chat", methods=["POST"])
def webui_chat() -> Any:
    """
    Enhanced chat endpoint that returns RAG chunks metadata.

    Request body:
    - messages: list of message dicts
    - model: optional model name
    - temperature: optional (0.0-2.0)
    - top_p: optional (0.0-1.0)
    - reasoning_level: optional
    - code_only: optional bool
    - prompt_name: optional override (otherwise from saved LLM Proxy settings)
    - include_rag_metadata: optional bool (default True for WebUI)
    """
    start_time = time.time()
    try:
        body = request.get_json(force=True, silent=True) or {}
        messages = body.get("messages") or []
        if not messages:
            return _error_response("messages is required", 400)

        # Unified path: delegate to /v1 core (single RAG implementation).
        proxy_body: dict[str, Any] = dict(body)
        proxy_body["messages"] = messages
        proxy_body["stream"] = False
        if "include_rag_metadata" not in proxy_body:
            proxy_body["include_rag_metadata"] = True
        if bool(body.get("code_only")) and isinstance(proxy_body.get("messages"), list):
            _msgs = [m for m in proxy_body.get("messages", []) if isinstance(m, dict)]
            if _msgs:
                for i in range(len(_msgs) - 1, -1, -1):
                    if str(_msgs[i].get("role") or "") == "user":
                        _c = str(_msgs[i].get("content") or "")
                        _msgs[i] = dict(_msgs[i], content=f"Only code, no explanations. {_c}".strip())
                        break
                proxy_body["messages"] = _msgs
        return _run_unified_proxy_chat(proxy_body)

    except Exception as e:
        _ERROR_LOG.error("webui_routes.webui_chat", exc_info=True)
        log_to_database("ERROR", str(e), source="webui_routes.webui_chat", error_type=type(e).__name__)
        return _error_response(e)
    finally:
        set_proxy_status(STATUS_IDLE)
        set_latest_request_seconds(time.time() - start_time)


@webui_bp.route("/dev-console", methods=["GET"])
def get_dev_console() -> Any:
    """Return recent requests from in-memory buffer for dev console."""
    try:
        limit = int(request.args.get("limit", 20))
        return jsonify({
            "requests": list(_REQUEST_BUFFER)[-limit:],
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_dev_console", exc_info=True)
        return _error_response(e)


@webui_bp.route("/model-settings", methods=["GET"])
def get_model_settings() -> Any:
    """Get current model settings."""
    try:
        settings_repo = get_settings_repository()

        default_provider_id = _default_llm_provider_id()
        stored_provider_id, stored_model = _read_app_provider_model_ref(
            settings_repo,
            provider_key="proxy_provider_id",
            model_key="proxy_model",
            fallback_provider=default_provider_id,
        )
        stored_settings_json = settings_repo.get_app_setting("proxy_settings")
        stored_rag_col = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip()
        stored_autocomplete_provider_id, stored_autocomplete = _read_app_provider_model_ref(
            settings_repo,
            provider_key="proxy_autocomplete_provider_id",
            model_key="proxy_autocomplete_model",
            fallback_provider=default_provider_id,
        )

        out: dict[str, Any] = {
            "provider_id": stored_provider_id,
            "model": stored_model,
            "autocomplete_provider_id": stored_autocomplete_provider_id,
            "prompt_name": "",
            "temperature": get_rag_float("temperature", 0.0),
            "top_p": get_rag_float("top_p", 0.1),
            "reasoning_level": "",
            "code_only": False,
            "include_rag_metadata": True,
            "fetch_web_knowledge": False,
            "web_interaction_enabled": False,
            "web_interaction_on_keywords": True,
            "web_interaction_on_low_confidence_framework": True,
            "web_interaction_ddg_news": False,
            "web_interaction_fetch_page": False,
            "web_interaction_wikipedia": False,
            "rag_collection": stored_rag_col,
            "autocomplete_model": stored_autocomplete,
        }

        if stored_settings_json:
            try:
                blob = json.loads(stored_settings_json)
                for key, val in blob.items():
                    if key in out:
                        out[key] = val
                    elif key == "model" and not out["model"]:
                        out["model"] = str(val or "").strip()
                if not out["provider_id"] and out["model"]:
                    out["provider_id"] = default_provider_id
                if not out["autocomplete_provider_id"] and out["autocomplete_model"]:
                    out["autocomplete_provider_id"] = default_provider_id
            except json.JSONDecodeError:
                pass

        pn = str(out.get("prompt_name") or "").strip()
        try:
            q_names = set(_get_qdrant_collection_names() or [])
        except Exception:
            q_names = set()
        rc = str(out.get("rag_collection") or "").strip()

        out["model_missing"] = not out["model"]
        out["prompt_missing"] = (not pn) or (not rag_prompt_file_exists(pn)) or is_readme_name(pn)
        out["collection_missing"] = bool(rc) and bool(q_names) and rc not in q_names

        return jsonify(out)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_model_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/status", methods=["GET"])
def llm_proxy_status() -> Any:
    """Base URL for WebUI RAG Fusion Proxy Status card (per-build Ollama tags live on builds, not here)."""
    try:
        bind_host = get_server_host()
        display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
        port = get_server_port()
        base_url = f"http://{display_host}:{port}"
        payload: dict[str, Any] = {
            "enabled": True,
            "base_url": base_url,
            "health": f"{base_url}/health",
        }
        return jsonify(payload)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.llm_proxy_status", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/api-key", methods=["GET"])
def llm_proxy_api_key_status() -> Any:
    """Return public metadata for the WebUI-managed Chiron /v1 API key."""
    try:
        return jsonify(proxy_api_key_status(get_settings_repository()))
    except Exception as e:
        _ERROR_LOG.error("webui_routes.llm_proxy_api_key_status", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/api-key/generate", methods=["POST"])
def llm_proxy_generate_api_key() -> Any:
    """Create or rotate the Chiron /v1 API key. Plaintext is returned only here."""
    try:
        settings_repo = get_settings_repository()
        plaintext, record = generate_proxy_api_key_record(settings_repo)
        store_proxy_api_key_record(settings_repo, record)
        payload = {
            "key": plaintext,
            **proxy_api_key_status(settings_repo),
        }
        return jsonify(payload)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.llm_proxy_generate_api_key", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/api-key/reveal", methods=["POST"])
def llm_proxy_reveal_api_key() -> Any:
    """Return the recoverable Chiron /v1 API key for WebUI admin reuse."""
    try:
        settings_repo = get_settings_repository()
        plaintext = reveal_proxy_api_key(settings_repo)
        if not plaintext:
            return _error_response("Chiron proxy API key is not recoverable", 404)
        return jsonify({"key": plaintext, **proxy_api_key_status(settings_repo)})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.llm_proxy_reveal_api_key", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/api-key", methods=["DELETE"])
def llm_proxy_delete_api_key() -> Any:
    """Delete the Chiron /v1 API key and close protected routes until regenerated."""
    try:
        settings_repo = get_settings_repository()
        delete_proxy_api_key_record(settings_repo)
        return jsonify(proxy_api_key_status(settings_repo))
    except Exception as e:
        _ERROR_LOG.error("webui_routes.llm_proxy_delete_api_key", exc_info=True)
        return _error_response(e)


@webui_bp.route("/model-settings", methods=["POST"])
def update_model_settings() -> Any:
    """Update model settings (persisted to app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        if body.get("provider_id") is not None:
            settings_repo.set_app_setting("proxy_provider_id", str(body.get("provider_id") or "").strip())
        if body.get("model") is not None:
            settings_repo.set_app_setting("proxy_model", str(body["model"]))
        if body.get("autocomplete_provider_id") is not None:
            settings_repo.set_app_setting(
                "proxy_autocomplete_provider_id",
                str(body.get("autocomplete_provider_id") or "").strip(),
            )
        if body.get("autocomplete_model") is not None:
            settings_repo.set_app_setting("proxy_autocomplete_model", str(body.get("autocomplete_model") or "").strip())
        if body.get("rag_collection") is not None:
            ConsumerRagBindings(settings_repo).set_stored_collection(
                RagConsumer.LLM_PROXY, str(body.get("rag_collection") or "").strip()
            )
        existing_blob: dict[str, Any] = {}
        try:
            raw_ps = settings_repo.get_app_setting("proxy_settings")
            if raw_ps:
                existing_blob = json.loads(raw_ps)
                if not isinstance(existing_blob, dict):
                    existing_blob = {}
        except (json.JSONDecodeError, TypeError):
            existing_blob = {}
        merged = {
            **existing_blob,
            **{
                k: v
                for k, v in body.items()
                if k not in {"provider_id", "autocomplete_provider_id"}
            },
        }
        settings_repo.set_app_setting("proxy_settings", json.dumps(merged))
        return jsonify({"status": "ok", "settings": merged})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_model_settings", exc_info=True)
        return _error_response(e)


def _ollama_tag_name_set_for_builds_diag() -> set[str]:
    cache_key = f"llm_proxy_builds_diag_ollama_names:{_get_ollama_url().rstrip('/')}"
    cached = _get_cached_status(
        cache_key,
        ttl_sec=3.0,
        compute=lambda: {"names": sorted(_fetch_ollama_tag_name_set_for_builds_diag(timeout_sec=0.8))},
    )
    return set(cached.get("names") or [])


def _fetch_ollama_tag_name_set_for_builds_diag(timeout_sec: float) -> set[str]:
    names: set[str] = set()
    try:
        url = _get_ollama_url().rstrip("/")
        data = invoke_tags(base_url=url, timeout=timeout_sec)
        for m in data.get("models") or []:
            if not isinstance(m, dict):
                continue
            n = (m.get("name") or m.get("model") or "").strip()
            if n:
                names.add(n)
    except Exception:
        pass
    return names


def _enrich_builds_with_diagnostics(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_o = pool.submit(_ollama_tag_name_set_for_builds_diag)
        fut_q = pool.submit(_get_cached_qdrant_collection_name_set_for_builds_diag)
        ollama_names = fut_o.result()
        qset = fut_q.result()
    out: list[dict[str, Any]] = []
    for b in builds:
        row = dict(b)
        row["use_prompt_template"] = b.get("use_prompt_template", True) is not False
        issues, healthy = diagnose_build(
            b,
            ollama_tag_names=ollama_names,
            prompt_exists=rag_prompt_file_exists(str(b.get("prompt_name") or "").strip()),
            qdrant_collection_names=qset,
        )
        row["issues"] = issues
        row["healthy"] = healthy
        out.append(row)
    return out


def _light_build_rows_for_webui(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same shape as enriched builds but without Ollama/Qdrant/prompt diagnostics (fast first paint)."""
    out: list[dict[str, Any]] = []
    for b in builds:
        row = dict(b)
        row["use_prompt_template"] = b.get("use_prompt_template", True) is not False
        row["issues"] = []
        row["healthy"] = True
        out.append(row)
    return out


@webui_bp.route("/llm-proxy/builds", methods=["GET"])
def get_llm_proxy_builds() -> Any:
    """List LLM Proxy builds with validation hints for WebUI."""
    try:
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        builds = load_builds_json(raw)
        diag_raw = (request.args.get("diagnostics") or "1").strip().lower()
        include_diagnostics = diag_raw not in ("0", "false", "no", "off")
        if include_diagnostics:
            enriched = _enrich_builds_with_diagnostics(builds)
        else:
            enriched = _light_build_rows_for_webui(builds)
        sh = get_server_host()
        dh = "127.0.0.1" if sh in ("0.0.0.0", "::", "") else sh
        main_port = get_server_port()
        return jsonify(
            {
                "builds": enriched,
                "openai_models_urls": {
                    "main": f"http://{dh}:{main_port}/v1/models",
                },
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_llm_proxy_builds", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/builds", methods=["PUT"])
def put_llm_proxy_builds() -> Any:
    """Replace full builds list (atomic validation)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw_list = body.get("builds")
        if not isinstance(raw_list, list):
            return _error_response("builds must be a JSON array", 400)
        normalized, errs = validate_builds_list([x for x in raw_list if isinstance(x, dict)])
        if normalized is None:
            return _error_response(_ValidationError("validation failed", details=errs))
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting(LLM_PROXY_BUILDS_APP_KEY, dump_builds_json(normalized))
        enriched = _enrich_builds_with_diagnostics(normalized)
        return jsonify({"ok": True, "builds": enriched})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.put_llm_proxy_builds", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/builds/<build_id>", methods=["GET"])
def get_llm_proxy_build_one(build_id: str) -> Any:
    """Single build by id with diagnostics."""
    try:
        if ".." in build_id or "/" in build_id or "\\" in build_id:
            return _error_response("Invalid id", 400)
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        builds = load_builds_json(raw)
        b = find_build_by_id(builds, build_id)
        if not b:
            return _error_response("not found", 404)
        enriched = _enrich_builds_with_diagnostics([b])[0]
        return jsonify({"build": enriched})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_llm_proxy_build_one", exc_info=True)
        return _error_response(e)


@webui_bp.route("/llm-proxy/builds/preview-model", methods=["POST"])
def llm_proxy_build_preview_model() -> Any:
    """Ollama show: context_length + thinking support for form helpers."""
    body = request.get_json(force=True, silent=True) or {}
    provider_id = str(body.get("provider_id") or "").strip() or _default_llm_provider_id()
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model is required"}), 400
    try:
        result = _run_provider_extension_action(provider_id, "show_model", {"selected_model": model})
        details = result.get("details") if isinstance(result, dict) else {}
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    ctx_len = extract_context_length_from_show(details if isinstance(details, dict) else None)
    caps = None
    if isinstance(details, dict):
        c = details.get("capabilities")
        if isinstance(c, list):
            caps = [str(x).strip().lower() for x in c if isinstance(x, str)]
    thinking = False
    if caps:
        thinking = "thinking" in caps or "think" in caps
    return jsonify(
        {
            "ok": True,
            "context_length": ctx_len,
            "supports_thinking": thinking,
            "capabilities": caps or [],
        }
    )



@webui_bp.route("/tester-settings", methods=["GET"])
def get_tester_settings() -> Any:
    """Get Model Tester settings for a session."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return _error_response("session_id is required", 400)
        
        settings_repo = get_settings_repository()
        settings = settings_repo.get_tester_settings(session_id)
        
        if not settings:
            return jsonify({
                "model": "",
                "prompt_name": "",
                "temperature": 0.0,
                "top_p": 0.1,
                "reasoning_level": "",
                "use_rag": True,
                "top_k": get_rag_int("top_k", 4),
                "rag_collection": "",
                "fetch_web_knowledge": False,
            })
        
        # Ensure rag_collection field exists
        if "rag_collection" not in settings:
            settings["rag_collection"] = ""
        if "fetch_web_knowledge" not in settings:
            settings["fetch_web_knowledge"] = False

        return jsonify(settings)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_tester_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/tester-settings", methods=["POST"])
def update_tester_settings() -> Any:
    """Save Model Tester settings for a session."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        
        if not session_id:
            return _error_response("session_id is required", 400)
        
        settings_repo = get_settings_repository()
        settings_repo.save_tester_settings(session_id, body)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_tester_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/tester/chat", methods=["POST"])
def tester_chat() -> Any:
    """Model Tester chat endpoint (with or without RAG)."""
    start_time = time.time()
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        messages = body.get("messages") or []
        use_rag = body.get("use_rag", True)
        fetch_web_knowledge = body.get("fetch_web_knowledge", False)
        provider_id = str(body.get("provider_id") or "").strip()
        model = body.get("model")
        prompt_name = body.get("prompt_name")
        temperature = body.get("temperature")
        top_p = body.get("top_p")
        reasoning_level = body.get("reasoning_level")
        top_k = body.get("top_k")
        
        if not messages:
            return _error_response("messages is required", 400)
        
        if not session_id:
            return _error_response("session_id is required", 400)

        # Get tester settings if not provided
        settings_repo = get_settings_repository()
        tester_settings = settings_repo.get_tester_settings(session_id) if session_id else None
        if tester_settings:
            provider_id = provider_id or str(tester_settings.get("provider_id") or "").strip()
            model = model or tester_settings.get("model")
            prompt_name = prompt_name or tester_settings.get("prompt_name")
            temperature = temperature if temperature is not None else tester_settings.get("temperature")
            top_p = top_p if top_p is not None else tester_settings.get("top_p")
            reasoning_level = reasoning_level or tester_settings.get("reasoning_level")
            use_rag = use_rag if "use_rag" in body else tester_settings.get("use_rag", True)
            top_k = top_k if top_k is not None else tester_settings.get("top_k")
            if "fetch_web_knowledge" not in body:
                fetch_web_knowledge = tester_settings.get("fetch_web_knowledge", False)
        if not (str(model).strip() if model is not None else ""):
            model = (settings_repo.get_app_setting("proxy_model") or "").strip() or model

        # Resolve optional collection/prompt from tester settings and delegate to unified /v1 path.
        collection_name = (body.get("collection_name") or "").strip() or None
        if not collection_name and tester_settings:
            collection_name = (tester_settings.get("rag_collection") or "").strip() or None
        if not collection_name:
            collection_name = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip() or None
        prompt_name = (prompt_name or "").strip() if isinstance(prompt_name, str) else str(prompt_name or "").strip()
        model_req = (str(model).strip() if model is not None else "")
        if not bool(use_rag):
            webui_dir = os.path.join(_ROOT, "WebUI") if os.path.isdir(os.path.join(_ROOT, "WebUI")) else None
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
            use_model = model_req or (params.model_name if params else "")
            use_model = (str(use_model or "")).strip()
            if not use_model:
                return _error_response("model is required", 400)
            options: dict[str, Any] = {}
            if temperature is not None:
                try:
                    options["temperature"] = float(temperature)
                except (TypeError, ValueError):
                    pass
            if top_p is not None:
                try:
                    options["top_p"] = float(top_p)
                except (TypeError, ValueError):
                    pass
            svc = current_app.extensions.get("llm_extensions_service")
            runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
            # Preserve the legacy direct-chat path when no provider is selected so
            # older tests and monkeypatch-based integrations still hit deps.chat_client.
            if runtime is not None and provider_id:
                from llm_interactor.contracts import LLMRequest

                resp = runtime.invoke(
                    LLMRequest(
                        provider_id=provider_id or _default_llm_provider_id(),
                        model=use_model,
                        operation="chat",
                        messages=[m for m in messages if isinstance(m, dict)],
                        stream=False,
                        options=(options or None),
                    )
                )
                content = resp.text or ""
            else:
                content = deps.chat_client.chat(messages, use_model, stream=False, options=(options or None)) or ""
            return jsonify(
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": use_model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "latency_ms": int((time.time() - start_time) * 1000),
                }
            )

        proxy_body: dict[str, Any] = {
            "messages": messages,
            "stream": False,
            "include_rag_metadata": bool(use_rag),
            "skip_rag": (not bool(use_rag)),
            "fetch_web_knowledge": bool(fetch_web_knowledge),
        }
        if model_req:
            proxy_body["model"] = model_req
        if provider_id:
            proxy_body["provider_id"] = provider_id
        if collection_name:
            proxy_body["collection_name"] = collection_name
        if prompt_name:
            proxy_body["prompt_name"] = prompt_name
        if temperature is not None:
            proxy_body["temperature"] = temperature
        if top_p is not None:
            proxy_body["top_p"] = top_p
        if reasoning_level:
            proxy_body["reasoning_level"] = reasoning_level
        return _run_unified_proxy_chat(proxy_body)

    except Exception as e:
        _ERROR_LOG.error("webui_routes.tester_chat", exc_info=True)
        return _error_response(e)


@webui_bp.route("/testing/external-docs/preview", methods=["POST"])
def testing_external_docs_preview() -> Any:
    """
    Testing-only endpoint: discover a GitHub repo by library name, fetch a bounded set of markdown docs,
    and return raw + MD-pipeline-processed markdown for inspection (no indexing, no Qdrant writes).
    """
    if run_pipeline is None:
        return _error_response("md_indexer module not available", 500)
    if not _EXTERNAL_DOCS_RAG_AVAILABLE:
        return _error_response("external_docs_rag module not available", 500)
    try:
        body = request.get_json(force=True, silent=True) or {}
        library = (body.get("library") or body.get("name") or "").strip()
        if not library:
            return _error_response("library is required", 400)

        # Guardrails: clamp payload sizes.
        max_files_raw = body.get("max_files")
        max_chars_raw = body.get("max_chars_per_file")
        pipeline_name = body.get("pipeline_name")

        try:
            max_files = int(max_files_raw) if max_files_raw is not None else 10
        except Exception:
            max_files = 10
        max_files = max(1, min(50, max_files))

        try:
            max_chars_per_file = int(max_chars_raw) if max_chars_raw is not None else 80000
        except Exception:
            max_chars_per_file = 80000
        max_chars_per_file = max(2000, min(300000, max_chars_per_file))

        if pipeline_name is None and get_active_pipeline_name is not None:
            pipeline_name = get_active_pipeline_name()

        from external_docs_rag.infrastructure import HttpFetchClient
        from external_docs_rag.infrastructure.github_discovery import (
            GITHUB_RAW_TEMPLATE,
            discover_repo,
        )
        from external_docs_rag.infrastructure.github_tree import list_markdown_paths
        from external_docs_rag.infrastructure.parsing import parse_document_to_markdown

        resolved = discover_repo(library)
        if not resolved:
            return jsonify({
                "ok": True,
                "library": library,
                "resolved": {
                    "found": False,
                    "label": library,
                    "repo_full_name": None,
                    "primary_url": None,
                },
                "pipeline": {"name": pipeline_name or "", "applied": True},
                "documents": [],
            })

        full_name, default_branch = resolved
        owner, repo = full_name.split("/", 1)
        ref = default_branch or "main"

        paths = list_markdown_paths(owner, repo, ref, max_depth=3)
        # Prefer README first if present.
        paths_sorted: list[str] = []
        for p in paths:
            if p.lower() == "readme.md":
                paths_sorted.insert(0, p)
            else:
                paths_sorted.append(p)
        paths_sorted = paths_sorted[:max_files]

        primary_url = GITHUB_RAW_TEMPLATE.format(full_name=full_name, ref=ref)

        if not paths_sorted:
            return jsonify({
                "ok": True,
                "library": library,
                "resolved": {
                    "found": True,
                    "label": library,
                    "repo_full_name": full_name,
                    "primary_url": primary_url,
                },
                "pipeline": {"name": pipeline_name or "", "applied": True},
                "documents": [],
            })

        fetch_client = HttpFetchClient()

        documents: list[dict[str, Any]] = []
        for path in paths_sorted:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
            raw_md = ""
            processed_md = ""
            err: str | None = None
            try:
                doc = fetch_client.fetch(url)
                if doc is None:
                    raise RuntimeError("Fetch failed")
                md = parse_document_to_markdown(doc) or ""
                raw_md = md[:max_chars_per_file]
                _, processed_md = run_pipeline(pipeline_name or "", raw_md)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            documents.append({
                "filename": path,
                "url": url,
                "raw_md": raw_md,
                "processed_md": processed_md,
                "error": err,
            })

        primary_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{paths_sorted[0]}"
        return jsonify({
            "ok": True,
            "library": library,
            "resolved": {
                "found": True,
                "label": library,
                "repo_full_name": full_name,
                "primary_url": primary_url,
            },
            "pipeline": {"name": pipeline_name or "", "applied": True},
            "documents": documents,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.testing_external_docs_preview", exc_info=True)
        return _error_response(e)


@webui_bp.route("/tester/prompt-preview", methods=["POST"])
def tester_prompt_preview() -> Any:
    """Return a preview of the full prompt that will be sent from Model Tester.

    Includes:
    - The raw system template prefix (as before, for backward compatibility)
    - The fully composed system message (prefix + context placeholder + suffix)
    - A preview of the chat messages list with the user message in its final position
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        prompt_name = (body.get("prompt_name") or "").strip() or get_rag_prompt_name()
        user_message = body.get("user_message") or ""
        use_rag = bool(body.get("use_rag", True))

        prefix, suffix = get_rag_system_prompt(prompt_name)

        # Build a representative system message using the same logic as runtime chat,
        # but with a lightweight placeholder instead of real RAG context.
        try:
            confidence_threshold = get_rag_float("confidence_threshold", 0.75)
        except Exception:
            confidence_threshold = 0.75
        try:
            model_name = _legacy_default_chat_model()
        except Exception:
            model_name = ""

        if use_rag:
            context_block = (
                "<<RAG CONTEXT (retrieved documentation snippets) WILL BE INSERTED HERE>>"
            )
        else:
            context_block = "<<RAG IS DISABLED — no context snippets will be added>>"

        system_full = build_system_content(
            prefix or "",
            suffix or "",
            context_block,
            confidence_threshold,
            confidence_threshold,
            None,
            model_name or "",
        )

        preview_messages = [
            {"role": "system", "content": system_full},
            {
                "role": "user",
                "content": user_message or "<<your next chat message will be inserted here>>",
            },
        ]

        return jsonify(
            {
                "prompt_name": prompt_name,
                # Kept for backward compatibility with older frontends
                "system_prompt": prefix or "",
                # New fields for full prompt visualization
                "system_message_full": system_full,
                "preview_messages": preview_messages,
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.tester_prompt_preview", exc_info=True)
        return _error_response(e)


@webui_bp.route("/settings", methods=["GET"])
def get_settings() -> Any:
    """Get app settings."""
    try:
        settings_repo = get_settings_repository()
        settings = settings_repo.get_all_app_settings()
        # Ensure rag_collection field exists
        if "rag_collection" not in settings:
            settings["rag_collection"] = ""
        return jsonify(settings)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/settings", methods=["POST"])
def update_settings() -> Any:
    """Update app settings."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        
        for key, value in body.items():
            settings_repo.set_app_setting(key, str(value))
        
        return jsonify({"status": "ok"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-keyword-collections", methods=["GET"])
def get_rag_keyword_collections() -> Any:
    """Return all RAG trigger keyword collections (from rag_service module)."""
    if get_keyword_collections_repository is None:
        return jsonify({"collections": []})
    try:
        repo = get_keyword_collections_repository()
        collections = repo.get_all()
        return jsonify({"collections": collections})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_rag_keyword_collections", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-keyword-collections", methods=["POST"])
def update_rag_keyword_collections() -> Any:
    """Create or update a collection, or replace all. Body: single {id?, name, enabled, keywords} or {collections: [...]}."""
    if get_keyword_collections_repository is None:
        return _error_response("Keyword collections not available", 503)
    try:
        body = request.get_json(force=True, silent=True) or {}
        repo = get_keyword_collections_repository()
        if "collections" in body:
            # Replace all: upsert each (use None for id when creating new), then delete IDs no longer in list
            new_list = body["collections"]
            existing_ids = {c["id"] for c in repo.get_all()}
            new_ids = set()
            for c in new_list:
                cid = c.get("id")
                if cid is None or (isinstance(cid, str) and cid.startswith("new-")):
                    cid = None
                elif cid not in existing_ids:
                    cid = None
                saved_id = repo.save_collection(
                    cid,
                    c.get("name", ""),
                    bool(c.get("enabled", True)),
                    c.get("keywords", []),
                )
                new_ids.add(saved_id)
            for cid in existing_ids - new_ids:
                repo.delete_collection(cid)
            return jsonify({"status": "ok", "collections": repo.get_all()})
        # Single collection create/update
        cid = repo.save_collection(
            body.get("id"),
            body.get("name", ""),
            bool(body.get("enabled", True)),
            body.get("keywords", []),
        )
        return jsonify({"status": "ok", "id": cid, "collections": repo.get_all()})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_keyword_collections", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-keyword-collections/<collection_id>", methods=["DELETE"])
def delete_rag_keyword_collection(collection_id: str) -> Any:
    """Delete a RAG keyword collection."""
    if get_keyword_collections_repository is None:
        return _error_response("Keyword collections not available", 503)
    try:
        repo = get_keyword_collections_repository()
        repo.delete_collection(collection_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_rag_keyword_collection", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-trigger-settings", methods=["GET"])
def get_rag_trigger_settings() -> Any:
    """Return RAG trigger threshold (effective from settings or config) and help table for scoring."""
    try:
        threshold = _get_effective_rag_trigger_threshold()
        return jsonify({
            "rag_trigger_threshold": threshold,
            "trigger_help_table": RAG_TRIGGER_HELP_ROWS,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_rag_trigger_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-trigger-settings", methods=["POST"])
def update_rag_trigger_settings() -> Any:
    """Update RAG trigger threshold (persisted to app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("rag_trigger_threshold")
        if raw is None:
            return _error_response("rag_trigger_threshold required", 400)
        val = int(raw)
        if val < 0 or val > 20:
            return _error_response("rag_trigger_threshold must be between 0 and 20", 400)
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting("rag_trigger_threshold", str(val))
        return jsonify({"status": "ok", "rag_trigger_threshold": val})
    except ValueError:
        return _error_response("rag_trigger_threshold must be an integer", 400)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_trigger_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-framework-settings", methods=["GET"])
def get_rag_framework_settings() -> Any:
    """
    Return framework docs RAG settings such as latest TTL days.
    """
    try:
        settings_repo = get_settings_repository()
        raw_ttl = settings_repo.get_app_setting("framework_latest_ttl_days")
        ttl_days = int(raw_ttl) if raw_ttl is not None else 90
        if ttl_days <= 0:
            ttl_days = 90
        return jsonify(
            {
                "framework_latest_ttl_days": ttl_days,
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_rag_framework_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-framework-settings", methods=["POST"])
def update_rag_framework_settings() -> Any:
    """
    Update framework docs RAG settings (e.g. latest TTL days).
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw_ttl = body.get("framework_latest_ttl_days")
        if raw_ttl is None:
            return _error_response("framework_latest_ttl_days required", 400)
        ttl_days = int(raw_ttl)
        if ttl_days <= 0 or ttl_days > 3650:
            return _error_response("framework_latest_ttl_days must be between 1 and 3650", 400)
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting("framework_latest_ttl_days", str(ttl_days))
        return jsonify({"status": "ok", "framework_latest_ttl_days": ttl_days})
    except ValueError:
        return _error_response("framework_latest_ttl_days must be an integer", 400)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_framework_settings", exc_info=True)
        return _error_response(e)


def _retrieval_yaml_raw_bool(key: str) -> bool:
    """Bool as stored in merged retrieval YAML (before WebUI proxy_settings override)."""
    try:
        from config import RETRIEVAL_CONFIG

        v = RETRIEVAL_CONFIG.get(key, False)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(v, (int, float)):
            return bool(v)
        return bool(v)
    except Exception:
        return False


def _get_rag_pipeline_definition_payload() -> list[dict[str, Any]]:
    try:
        from rag_service.application import get_rag_pipeline_definition

        steps = get_rag_pipeline_definition()
        if isinstance(steps, list):
            return [dict(s) for s in steps if isinstance(s, dict)]
    except Exception:
        pass
    return []


def _get_proxy_pipeline_definition_payload() -> list[dict[str, Any]]:
    try:
        from llm_proxy.pipeline_steps import get_proxy_pipeline_definition

        steps = get_proxy_pipeline_definition()
        if isinstance(steps, list):
            return [dict(s) for s in steps if isinstance(s, dict)]
    except Exception:
        pass
    return []


def _get_proxy_last_executed_steps_payload() -> list[dict[str, Any]]:
    trace = get_current_trace()
    if not isinstance(trace, dict):
        return []
    raw = trace.get("pipeline_steps")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        out.append(
            {
                "id": sid,
                "status": str(item.get("status") or ""),
                "reason": item.get("reason"),
            }
        )
    return out


def _default_llm_provider_id() -> str:
    wiring = current_app.extensions.get("llm_proxy_wiring")
    provider_id = getattr(wiring, "default_provider_id", None)
    if isinstance(provider_id, str) and provider_id.strip():
        return provider_id.strip()
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    try:
        descriptors = runtime.registry.descriptors() if runtime is not None else []
    except Exception:
        descriptors = []
    if descriptors:
        first_id = str(descriptors[0].id or "").strip()
        if first_id:
            return first_id
    return ""


def _provider_catalog_payload(*, capability: str | None = None) -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if svc is None:
        return {"providers": [], "models": []}
    try:
        return svc.provider_catalog(runtime=runtime, capability=capability)
    except Exception:
        return {"providers": [], "models": []}


def _provider_row(provider_id: str | None = None) -> dict[str, Any] | None:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if svc is None:
        return None
    try:
        rows = svc.provider_rows(runtime)
    except Exception:
        return None
    resolved_provider_id = str(provider_id or _default_llm_provider_id()).strip()
    if resolved_provider_id:
        for row in rows:
            if str(row.get("provider_id") or "").strip() == resolved_provider_id:
                return row
    return rows[0] if rows else None


def _default_provider_row() -> dict[str, Any] | None:
    return _provider_row()


def _run_provider_extension_action(
    provider_id: str | None,
    action_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    row = _provider_row(provider_id)
    if svc is None or runtime is None or row is None:
        raise RuntimeError("No provider extension is available")
    extension_id = str(row.get("extension_id") or "").strip()
    if not extension_id:
        raise RuntimeError("Provider extension is missing extension_id")
    return svc.run_extension_action(
        extension_id,
        action_id,
        payload=dict(payload or {}),
        runtime=runtime,
    )


def _run_default_provider_extension_action(action_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return _run_provider_extension_action(_default_llm_provider_id(), action_id, payload)


def _default_provider_tab_payload() -> dict[str, Any]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    row = _default_provider_row()
    if svc is None or runtime is None or row is None:
        raise RuntimeError("No default provider extension is available")
    extension_id = str(row.get("extension_id") or "").strip()
    if not extension_id:
        raise RuntimeError("Default provider extension is missing extension_id")
    return svc.extension_tab_payload(extension_id, runtime=runtime)


def _invoke_runtime_chat(
    *,
    provider_id: str,
    model: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> str:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if runtime is None:
        raise RuntimeError("LLM runtime is unavailable")
    from llm_interactor.contracts import LLMRequest

    response = runtime.invoke(
        LLMRequest(
            provider_id=provider_id,
            model=model,
            operation="chat",
            messages=[m for m in messages if isinstance(m, dict)],
            stream=False,
            options=(options or None),
        )
    )
    return str(response.text or "")


def _invoke_runtime_embed(
    *,
    provider_id: str,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    svc = current_app.extensions.get("llm_extensions_service")
    runtime = current_app.extensions.get("llm_interactor_runtime") or getattr(svc, "runtime", None)
    if runtime is None:
        raise RuntimeError("LLM runtime is unavailable")
    from llm_interactor.contracts import LLMRequest

    response = runtime.invoke(
        LLMRequest(
            provider_id=provider_id,
            model=model,
            operation="embed",
            input_texts=[str(text) for text in texts],
        )
    )
    raw = response.raw if isinstance(response.raw, dict) else {}
    embeddings = raw.get("embeddings")
    if not isinstance(embeddings, list):
        raise RuntimeError("Provider returned invalid embeddings payload")
    out: list[list[float]] = []
    for item in embeddings:
        if isinstance(item, list):
            out.append([float(v) for v in item])
    if len(out) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(out)}")
    return out


def _read_app_provider_model_ref(
    settings_repo: Any,
    *,
    provider_key: str,
    model_key: str,
    fallback_provider: str | None = None,
) -> tuple[str, str]:
    provider_id = str(settings_repo.get_app_setting(provider_key) or "").strip()
    model = str(settings_repo.get_app_setting(model_key) or "").strip()
    if model and not provider_id:
        provider_id = str(fallback_provider or _default_llm_provider_id()).strip()
    return provider_id, model


def _read_dict_provider_model_ref(
    blob: dict[str, Any],
    *,
    provider_key: str,
    model_key: str,
    fallback_provider: str | None = None,
) -> tuple[str, str]:
    provider_id = str(blob.get(provider_key) or "").strip()
    model = str(blob.get(model_key) or "").strip()
    if model and not provider_id:
        provider_id = str(fallback_provider or _default_llm_provider_id()).strip()
    return provider_id, model


def _build_pipeline_definition_payload() -> dict[str, Any]:
    return {
        "rag": {"steps": _get_rag_pipeline_definition_payload()},
        "proxy": {"steps": _get_proxy_pipeline_definition_payload()},
    }


@webui_bp.route("/rag-model-settings", methods=["GET"])
def get_rag_model_settings() -> Any:
    """Return embedding + rerank model settings for RAG/Qdrant UI."""
    try:
        from application.rag.retrieval_ui_overrides import RETRIEVAL_UI_BOOL_KEYS, retrieval_bool_with_ui_override

        settings_repo = get_settings_repository()
        default_provider_id = _default_llm_provider_id()

        default_embed_model = _legacy_default_embed_model()
        default_rerank_model = _legacy_default_rerank_model()

        rag_embed_provider_id, rag_embed_model = _read_app_provider_model_ref(
            settings_repo,
            provider_key="rag_embed_provider_id",
            model_key="rag_embed_model",
            fallback_provider=default_provider_id,
        )

        proxy_settings = load_proxy_settings(settings_repo)

        rerank_for_rag = bool(proxy_settings.get("rerank_for_rag", False))
        rag_rerank_provider_id, raw_rerank_model = _read_dict_provider_model_ref(
            proxy_settings,
            provider_key="rag_rerank_provider_id",
            model_key="rerank_model",
            fallback_provider=default_provider_id,
        )
        # For UI convenience, if rerank is enabled but model missing, show default.
        rerank_model = raw_rerank_model if raw_rerank_model else (default_rerank_model if rerank_for_rag else "")
        if rerank_model and not rag_rerank_provider_id:
            rag_rerank_provider_id = default_provider_id

        yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
        hybrid_sparse_enabled, hybrid_source = resolve_hybrid_sparse_enabled(
            proxy_settings=proxy_settings,
            yaml_default=yaml_hybrid,
        )

        retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}

        return jsonify(
            {
                "rag_embed_provider_id": rag_embed_provider_id,
                "rag_embed_model": rag_embed_model,
                "rag_rerank_provider_id": rag_rerank_provider_id,
                "rerank_for_rag": rerank_for_rag,
                "rerank_model": rerank_model,
                "hybrid_sparse_enabled": hybrid_sparse_enabled,
                "retrieval_advanced": retrieval_advanced,
                "retrieval_yaml_defaults": retrieval_yaml_defaults,
                "defaults": {
                    "rag_embed_provider_id": default_provider_id,
                    "rag_embed_model": default_embed_model,
                    "rag_rerank_provider_id": default_provider_id,
                    "rerank_model": default_rerank_model,
                    "hybrid_sparse_enabled": yaml_hybrid,
                },
                "contract_sources": {
                    "hybrid_sparse_enabled": hybrid_source,
                    "rerank_for_rag": (
                        "proxy_settings.rerank_for_rag" if "rerank_for_rag" in proxy_settings else "default.false"
                    ),
                },
                "pipeline_definition": {
                    "rag": {"steps": _get_rag_pipeline_definition_payload()},
                },
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_rag_model_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/pipeline-preview", methods=["GET"])
def get_pipeline_preview() -> Any:
    """
    Snapshot of proxy/RAG pipeline flags for Web UI (GitLab-style diagram).
    Includes persisted proxy_settings, RAG collection name, hybrid/rerank, and WebInteraction env gates.
    """
    try:
        settings_repo = get_settings_repository()
        rag_col = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip()
        rag_collection_configured = bool(rag_col)

        proxy_settings = load_proxy_settings(settings_repo)

        fetch_web_knowledge = bool(proxy_settings.get("fetch_web_knowledge", False))
        rerank_for_rag = bool(proxy_settings.get("rerank_for_rag", False))
        yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
        hybrid_sparse_enabled, hybrid_source = resolve_hybrid_sparse_enabled(
            proxy_settings=proxy_settings,
            yaml_default=yaml_hybrid,
        )

        raw_news = False
        raw_fetch = False
        raw_wiki = False
        global_web = True
        try:
            from web_interaction.config import ddg_news_enabled, web_interaction_globally_enabled
            from web_interaction.fetch_excerpt import fetch_page_env_enabled
            from web_interaction.wikipedia_fallback import wikipedia_env_enabled

            global_web = web_interaction_globally_enabled()
            raw_news = ddg_news_enabled()
            raw_fetch = fetch_page_env_enabled()
            raw_wiki = wikipedia_env_enabled()
        except ImportError:
            pass

        web_flags = resolve_web_interaction_flags(
            proxy_settings=proxy_settings,
            env_ddg_news=raw_news,
            env_fetch_page=raw_fetch,
            env_wikipedia=raw_wiki,
        )

        env_payload = {
            "web_interaction_globally_enabled": global_web,
            "ddg_news": bool(web_flags["web_interaction_ddg_news"]["value"]),
            "fetch_page": bool(web_flags["web_interaction_fetch_page"]["value"]),
            "wikipedia": bool(web_flags["web_interaction_wikipedia"]["value"]),
        }
        env_raw_payload = {
            "ddg_news": raw_news,
            "fetch_page": raw_fetch,
            "wikipedia": raw_wiki,
        }

        return jsonify(
            {
                "rag_collection_configured": rag_collection_configured,
                "hybrid_sparse_enabled": hybrid_sparse_enabled,
                "rerank_for_rag": rerank_for_rag,
                "fetch_web_knowledge": fetch_web_knowledge,
                "web_interaction_enabled": bool(web_flags["web_interaction_enabled"]["value"]),
                "web_interaction_on_keywords": bool(web_flags["web_interaction_on_keywords"]["value"]),
                "web_interaction_on_low_confidence_framework": bool(
                    web_flags["web_interaction_on_low_confidence_framework"]["value"]
                ),
                "env": env_payload,
                "env_raw": env_raw_payload,
                "contract_sources": {
                    "hybrid_sparse_enabled": hybrid_source,
                    "web_interaction_enabled": str(web_flags["web_interaction_enabled"]["source"]),
                    "web_interaction_on_keywords": str(web_flags["web_interaction_on_keywords"]["source"]),
                    "web_interaction_on_low_confidence_framework": str(
                        web_flags["web_interaction_on_low_confidence_framework"]["source"]
                    ),
                    "web_interaction_ddg_news": str(web_flags["web_interaction_ddg_news"]["source"]),
                    "web_interaction_fetch_page": str(web_flags["web_interaction_fetch_page"]["source"]),
                    "web_interaction_wikipedia": str(web_flags["web_interaction_wikipedia"]["source"]),
                },
                "pipeline_definition": _build_pipeline_definition_payload(),
                "proxy_last_executed_steps": _get_proxy_last_executed_steps_payload(),
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_pipeline_preview", exc_info=True)
        return _error_response(e)


@webui_bp.route("/pipeline-definition", methods=["GET"])
def get_pipeline_definition() -> Any:
    """Canonical pipeline step definitions for Web UI (RAG + LLM proxy)."""
    try:
        return jsonify(
            {
                "pipeline_definition": _build_pipeline_definition_payload(),
                "proxy_last_executed_steps": _get_proxy_last_executed_steps_payload(),
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_pipeline_definition", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-model-settings", methods=["POST"])
def update_rag_model_settings() -> Any:
    """Persist embedding + rerank model settings for RAG/Qdrant UI."""
    try:
        from application.rag.retrieval_ui_overrides import RETRIEVAL_UI_BOOL_KEYS, retrieval_bool_with_ui_override

        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        default_provider_id = _default_llm_provider_id()

        default_rerank_model = _legacy_default_rerank_model()

        rag_embed_provider_id = str(body.get("rag_embed_provider_id") or "").strip() or default_provider_id
        rag_embed_model = str(body.get("rag_embed_model") or "").strip()
        settings_repo.set_app_setting("rag_embed_provider_id", rag_embed_provider_id)
        settings_repo.set_app_setting("rag_embed_model", rag_embed_model)

        rag_rerank_provider_id = str(body.get("rag_rerank_provider_id") or "").strip() or default_provider_id
        rerank_for_rag = bool(body.get("rerank_for_rag", False))
        rerank_model = str(body.get("rerank_model") or "").strip()
        yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
        hybrid_sparse_enabled = bool(body.get("hybrid_sparse_enabled", yaml_hybrid))

        proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
        proxy_settings: dict[str, Any] = {}
        if proxy_settings_json:
            try:
                proxy_settings = json.loads(proxy_settings_json) or {}
            except json.JSONDecodeError:
                proxy_settings = {}

        proxy_settings["rerank_for_rag"] = rerank_for_rag
        proxy_settings["hybrid_sparse_enabled"] = hybrid_sparse_enabled
        proxy_settings["rag_rerank_provider_id"] = rag_rerank_provider_id

        for rk in RETRIEVAL_UI_BOOL_KEYS:
            if rk in body:
                proxy_settings[rk] = bool(body.get(rk))

        # When enabled, default to a known-good reranker if user chose "Default".
        if rerank_for_rag:
            proxy_settings["rerank_model"] = rerank_model or default_rerank_model
        else:
            # Keep existing rerank_model if present; it's irrelevant when rerank_for_rag is false.
            if rerank_model:
                proxy_settings["rerank_model"] = rerank_model

        settings_repo.set_app_setting("proxy_settings", json.dumps(proxy_settings))

        default_embed_model = _legacy_default_embed_model()
        retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        return jsonify(
            {
                "status": "ok",
                "rag_embed_provider_id": rag_embed_provider_id,
                "rag_embed_model": rag_embed_model,
                "rag_rerank_provider_id": rag_rerank_provider_id,
                "rerank_for_rag": rerank_for_rag,
                "rerank_model": proxy_settings.get("rerank_model") or "",
                "hybrid_sparse_enabled": hybrid_sparse_enabled,
                "retrieval_advanced": retrieval_advanced,
                "retrieval_yaml_defaults": retrieval_yaml_defaults,
                "defaults": {
                    "rag_embed_provider_id": default_provider_id,
                    "rag_embed_model": default_embed_model,
                    "rag_rerank_provider_id": default_provider_id,
                    "rerank_model": default_rerank_model,
                    "hybrid_sparse_enabled": yaml_hybrid,
                },
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_model_settings", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag-trigger-test", methods=["POST"])
def rag_trigger_test() -> Any:
    """Check if a message would trigger RAG: returns score, signals, and triggered (score >= threshold)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        message = (body.get("message") or "").strip()
        threshold = _get_effective_rag_trigger_threshold()
        rag_keywords = _get_rag_required_keywords_from_module()
        score, signals, triggered = compute_rag_trigger_score(
            message,
            rag_required_keywords=rag_keywords,
            trigger_threshold=threshold,
        )
        return jsonify({
            "score": score,
            "signals": signals,
            "triggered": triggered,
            "threshold": threshold,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.rag_trigger_test", exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag/status", methods=["GET"])
def rag_status() -> Any:
    """Return Qdrant / RAG status (is running, version, collections count)."""
    status = _get_cached_status(
        "qdrant_status",
        ttl_sec=2.0,
        compute=lambda: _qdrant_status_snapshot(timeout_sec=0.6),
    )
    return jsonify(status)


def _get_gpu_metrics() -> dict[str, Any] | None:
    """Return first GPU metrics (utilization %, memory used/total MB, temp C) or None if unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0 or not result.stdout or not result.stdout.strip():
            return None
        line = result.stdout.strip().split("\n")[0].strip()
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            return None
        def _int_or_none(s: str) -> int | None:
            s = (s or "").strip()
            return int(s) if s.isdigit() else None
        util_s = (parts[0] or "").replace("%", "").strip()
        mem_used = (parts[1] or "").replace("MiB", "").replace("MB", "").strip()
        mem_total = (parts[2] or "").replace("MiB", "").replace("MB", "").strip()
        temp_s = (parts[3] or "").replace("C", "").strip() if len(parts) > 3 else ""
        return {
            "utilization_pct": _int_or_none(util_s),
            "memory_used_mb": _int_or_none(mem_used),
            "memory_total_mb": _int_or_none(mem_total),
            "temperature_c": _int_or_none(temp_s),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


@webui_bp.route("/dashboard-metrics", methods=["GET"])
def dashboard_metrics() -> Any:
    """Return metrics for dashboard header: RAG (collections count), Ollama running, optional GPU."""
    payload: dict[str, Any] = {"rag": {}, "ollama": {}, "gpu": None}
    q = _get_cached_status(
        "qdrant_status",
        ttl_sec=2.0,
        compute=lambda: _qdrant_status_snapshot(timeout_sec=0.6),
    )
    payload["rag"] = {
        "running": bool(q.get("running")),
        "collections_count": int(q.get("collections_count") or 0),
    }
    url_o = _get_ollama_url().rstrip("/")
    try:
        ping_o = invoke_ping(base_url=url_o, timeout=1.0)
        payload["ollama"] = {"running": bool(ping_o.get("ok"))}
    except Exception:
        payload["ollama"] = {"running": False}
    payload["gpu"] = _get_gpu_metrics()
    payload["proxy_status"] = get_proxy_status_label()
    payload["latest_request_seconds"] = get_latest_request_seconds()
    payload["latest_request_total_tokens"] = get_latest_request_total_tokens()
    payload["latest_request_rag_steps"] = get_latest_request_rag_steps()
    return jsonify(payload)


def _get_qdrant_collection_names() -> list[str]:
    """Return list of Qdrant collection names (empty if Qdrant unreachable or no collections)."""
    return _get_qdrant_collection_names_with_timeout(timeout_sec=5.0)


def _get_cached_qdrant_collection_name_set_for_builds_diag() -> set[str]:
    cache_key = f"llm_proxy_builds_diag_qdrant_names:{get_qdrant_url().rstrip('/')}"
    cached = _get_cached_status(
        cache_key,
        ttl_sec=3.0,
        compute=lambda: {"names": _get_qdrant_collection_names_with_timeout(timeout_sec=0.8)},
    )
    return set(cached.get("names") or [])


def _get_qdrant_collection_names_with_timeout(timeout_sec: float) -> list[str]:
    """Return Qdrant collection names using an explicit timeout."""
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=timeout_sec)
        if not resp.ok:
            return []
        data = resp.json() or {}
        raw = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw:
            if isinstance(col, dict):
                name = col.get("name")
            else:
                name = str(col)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


@webui_bp.route("/rag/collections", methods=["GET"])
def rag_collections() -> Any:
    """Return detailed information about Qdrant collections."""
    url = get_qdrant_url().rstrip("/")

    ttl_days = get_framework_collection_ttl_days()
    default_top_k = get_default_rag_top_k()
    try:
        settings_repo = get_settings_repository()
        ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
        if ttl_raw is not None and str(ttl_raw).strip() != "":
            try:
                ttl_days = int(ttl_raw)
            except (TypeError, ValueError):
                pass
        top_k_raw = settings_repo.get_app_setting("default_rag_top_k")
        if top_k_raw is not None and str(top_k_raw).strip() != "":
            try:
                default_top_k = int(top_k_raw)
            except (TypeError, ValueError):
                pass
    except Exception:
        pass

    try:
        resp = requests.get(f"{url}/collections", timeout=5)
    except requests.exceptions.RequestException as e:
        _WEBUI_LOG.warning("Qdrant unreachable at %s: %s", url, e)
        return jsonify({
            "collections": [],
            "error": "qdrant_unreachable",
            "ttl_days": ttl_days,
            "default_rag_top_k": default_top_k,
        })

    try:
        if not resp.ok:
            _WEBUI_LOG.warning("Qdrant /collections returned %s: %s", resp.status_code, resp.text)
            return jsonify({"collections": [], "error": f"HTTP {resp.status_code}"}), resp.status_code
        data = resp.json() or {}

        raw_collections = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw_collections:
            if isinstance(col, dict):
                name = col.get("name")
            else:
                name = str(col)
            if name:
                names.append(name)

        # Use official QdrantClient to fetch rich info for each collection
        client = QdrantClient(url=url)

        detailed: list[dict[str, Any]] = []
        for name in names:
            try:
                info = client.get_collection(name)
                # info.config.params contains shard/replication/ondisk
                params = getattr(getattr(info, "config", None), "params", None)
                points_count = getattr(info, "points_count", None)
                shards_count = getattr(params, "shard_number", None) if params else None
                replication_factor = getattr(params, "replication_factor", None) if params else None
                on_disk = bool(getattr(params, "on_disk_payload", False)) if params else False
                
                # Get segments count
                segments_count = getattr(info, "segments_count", None)
                
                # Extract vectors config
                vectors_config = None
                vectors_info = getattr(params, "vectors", None) if params else None
                if vectors_info:
                    # Check if it's NamedVectors (dict) or VectorParams (single vector)
                    if isinstance(vectors_info, dict):
                        # NamedVectors: multiple named vectors
                        # Take the first one or "Default" if exists
                        vector_name = "Default" if "Default" in vectors_info else next(iter(vectors_info.keys()), None)
                        if vector_name:
                            vec_params = vectors_info[vector_name]
                            if hasattr(vec_params, "size") and hasattr(vec_params, "distance"):
                                vectors_config = {
                                    "name": vector_name,
                                    "size": getattr(vec_params, "size"),
                                    "distance": str(getattr(vec_params, "distance", "")).split(".")[-1] if hasattr(vec_params, "distance") else None,
                                }
                    else:
                        # Single VectorParams
                        if hasattr(vectors_info, "size") and hasattr(vectors_info, "distance"):
                            vectors_config = {
                                "name": "Default",
                                "size": getattr(vectors_info, "size"),
                                "distance": str(getattr(vectors_info, "distance", "")).split(".")[-1] if hasattr(vectors_info, "distance") else None,
                            }

                item = {
                    "name": name,
                    "points_count": points_count,
                    "shards_count": shards_count,
                    "replication_factor": replication_factor,
                    "on_disk": on_disk,
                    "segments_count": segments_count,
                    "vectors_config": vectors_config,
                }
                # Registry meta for TTL display
                try:
                    settings_repo = get_settings_repository()
                    meta = settings_repo.get_collection_meta(name)
                    if meta:
                        item["last_refreshed_at"] = meta.get("last_refreshed_at")
                        item["framework_id"] = meta.get("framework_id")
                        item["version"] = meta.get("version")
                except Exception:
                    pass
                detailed.append(item)
            except Exception as e:
                _WEBUI_LOG.warning("Failed to get collection %s via QdrantClient: %s", name, e)
                detailed.append({"name": name})

        return jsonify({
            "collections": detailed,
            "ttl_days": ttl_days,
            "default_rag_top_k": default_top_k,
        })
    except Exception as e:
        _WEBUI_LOG.error("Failed to get Qdrant collections: %s", e, exc_info=True)
        return jsonify({
            "collections": [],
            "error": str(e),
            "ttl_days": ttl_days,
            "default_rag_top_k": default_top_k,
        }), 500


@webui_bp.route("/rag/collection-settings", methods=["POST"])
def save_rag_collection_settings() -> Any:
    """Save RAG collection settings: framework_collection_ttl_days, default_rag_top_k (stored in app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        if "ttl_days" in body:
            try:
                settings_repo.set_app_setting("framework_collection_ttl_days", str(int(body["ttl_days"])))
            except (TypeError, ValueError):
                pass
        if "default_rag_top_k" in body:
            try:
                settings_repo.set_app_setting("default_rag_top_k", str(int(body.get("default_rag_top_k", 4))))
            except (TypeError, ValueError):
                pass
        return jsonify({"status": "ok"})
    except Exception as e:
        _WEBUI_LOG.error("save_rag_collection_settings: %s", e, exc_info=True)
        return _error_response(e)


@webui_bp.route("/rag/start", methods=["POST"])
def rag_start() -> Any:
    """Try to start Qdrant Docker container (ServiceStarter: ensures Docker + pull/run/start)."""
    try:
        ok, output, name = start_qdrant_service()
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output, "container": name}), status
    except Exception as e:
        _WEBUI_LOG.error("rag_start: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e), "container": os.getenv("QDRANT_CONTAINER_NAME", "qdrant")}), 500


@webui_bp.route("/rag/stop", methods=["POST"])
def rag_stop() -> Any:
    """Try to stop Qdrant Docker container."""
    try:
        ok, output, name = stop_qdrant_service()
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output, "container": name}), status
    except Exception as e:
        _WEBUI_LOG.error("rag_stop: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e), "container": os.getenv("QDRANT_CONTAINER_NAME", "qdrant")}), 500


@webui_bp.route("/ollama/status", methods=["GET"])
def ollama_status() -> Any:
    """Legacy compatibility route backed by the default provider extension."""
    row = _default_provider_row()
    if row is None:
        return jsonify({"running": False, "error": "No default provider extension loaded"}), 503
    health = row.get("health") if isinstance(row.get("health"), dict) else {}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return jsonify(
        {
            "url": metadata.get("base_url") or metadata.get("chat_url") or None,
            "running": bool(health.get("ok")),
            "http_status": health.get("details", {}).get("status_code") if isinstance(health.get("details"), dict) else None,
            "error": health.get("message") or "",
        }
    )


@webui_bp.route("/ollama/start", methods=["POST"])
def ollama_start() -> Any:
    try:
        result = _run_default_provider_extension_action("start_service")
        status = 200 if bool(result.get("ok")) else 500
        return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
    except Exception as e:
        _WEBUI_LOG.error("ollama_start: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e)}), 500


@webui_bp.route("/ollama/stop", methods=["POST"])
def ollama_stop() -> Any:
    try:
        result = _run_default_provider_extension_action("stop_service")
        status = 200 if bool(result.get("ok")) else 500
        return jsonify({"ok": bool(result.get("ok")), "output": result.get("message") or ""}), status
    except Exception as e:
        _WEBUI_LOG.error("ollama_stop: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e)}), 500


@webui_bp.route("/ollama/library", methods=["GET"])
def ollama_library() -> Any:
    try:
        payload = _default_provider_tab_payload()
        schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
        rows: list[dict[str, Any]] = []
        hidden_ids: list[str] = []
        diagnostics = {}
        for page in schema.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for section in page.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                for component in section.get("components") or []:
                    if not isinstance(component, dict):
                        continue
                    if component.get("type") == "table" and component.get("key") == "provider_models":
                        rows = [dict(item) for item in component.get("rows") or [] if isinstance(item, dict)]
                    if component.get("type") == "diagnostics":
                        diagnostics = dict(component.get("value") or {})
        if isinstance(diagnostics.get("hidden_model_ids"), list):
            hidden_ids = [str(x) for x in diagnostics.get("hidden_model_ids") if str(x).strip()]
        models = [
            {
                "name": str(row.get("id") or ""),
                "size": row.get("size", 0),
                "modified_at": row.get("modified_at", ""),
                "digest": row.get("digest"),
                "hidden": bool(row.get("hidden")),
            }
            for row in rows
            if str(row.get("id") or "").strip()
        ]
        return jsonify({"ok": True, "url": diagnostics.get("base_url"), "models": models, "hidden_ids": hidden_ids})
    except Exception as e:
        _WEBUI_LOG.warning("ollama_library: %s", e)
        return jsonify(
            {
                "ok": False,
                "url": None,
                "models": [],
                "hidden_ids": [],
                "error": str(e),
            }
        )


@webui_bp.route("/ollama/hidden", methods=["PATCH"])
def ollama_hidden_patch() -> Any:
    body = request.get_json(silent=True) or {}
    raw_add = body.get("add")
    raw_remove = body.get("remove")
    add = raw_add if isinstance(raw_add, list) else []
    remove = raw_remove if isinstance(raw_remove, list) else []
    try:
        updated: list[str] = []
        for model_name in add:
            result = _run_default_provider_extension_action("hide_model", {"selected_model": str(model_name)})
            if isinstance(result.get("hidden_model_ids"), list):
                updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
        for model_name in remove:
            result = _run_default_provider_extension_action("unhide_model", {"selected_model": str(model_name)})
            if isinstance(result.get("hidden_model_ids"), list):
                updated = [str(x) for x in result.get("hidden_model_ids") if str(x).strip()]
        return jsonify({"ok": True, "hidden_ids": updated})
    except Exception as e:
        _WEBUI_LOG.error("ollama_hidden_patch: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@webui_bp.route("/ollama/show", methods=["POST"])
def ollama_show_model() -> Any:
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model is required"}), 400
    try:
        result = _run_default_provider_extension_action("show_model", {"selected_model": model})
        return jsonify({"ok": bool(result.get("ok", True)), "details": result.get("details") or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@webui_bp.route("/ollama/delete", methods=["POST"])
def ollama_delete_model() -> Any:
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model is required"}), 400
    try:
        result = _run_default_provider_extension_action("delete_model", {"selected_model": model})
        return jsonify({"ok": bool(result.get("ok", True)), "result": result.get("details") or result.get("result") or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@webui_bp.route("/ollama/pull", methods=["POST"])
def ollama_pull_stream() -> Any:
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return _error_response("model is required", 400)

    def generate():
        try:
            result = _run_default_provider_extension_action("pull_model", {"pull_model_name": model})
            yield json.dumps(result, ensure_ascii=False) + "\n"
        except Exception as e:
            _WEBUI_LOG.error("ollama_pull_stream: %s", e, exc_info=True)
            yield json.dumps({"error": str(e)}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _shutdown_server() -> None:
    """
    Trigger server shutdown.

    - If running under Werkzeug dev server, call its shutdown hook.
    - Otherwise (e.g. started from a different WSGI runner), fall back to os._exit(0)
      to terminate the process on this request.
    """
    func = request.environ.get("werkzeug.server.shutdown")
    if func is not None:
        func()
        return

    # Fallback: hard-exit the process. This is acceptable here because this
    # server is intended for local/dev usage, started via start_webui.bat.
    os._exit(0)


@webui_bp.route("/server/stop", methods=["POST"])
def server_stop() -> Any:
    """Stop the WebUI / RAG Proxy Flask server."""
    try:
        _WEBUI_LOG.info("Received WebUI shutdown request")
        _shutdown_server()
        return jsonify({"status": "stopping"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.server_stop", exc_info=True)
        return _error_response(e)


# ============================================================================
# Crawler / Indexer API Endpoints
# ============================================================================

def _get_crawler_sources_dir() -> str:
    """Get path to WebUI/rag_sources directory."""
    # Try to find WebUI directory relative to project root
    possible_paths = [
        os.path.join(_ROOT, "WebUI", "rag_sources"),
        os.path.join(os.path.dirname(_ROOT), "WebUI", "rag_sources"),
    ]
    for path in possible_paths:
        if os.path.isdir(path):
            return path
    # Fallback: assume WebUI is sibling to api directory
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    webui_dir = os.path.join(os.path.dirname(api_dir), "WebUI", "rag_sources")
    return webui_dir


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


def _point_id_from_hash(h: str) -> int:
    """Build a Qdrant-compatible unsigned integer point id from a sha256 hex string."""
    h = (h or "0" * 16)[:16]
    return int(h, 16)


def _get_embeddings_simple(
    texts: list[str],
    *,
    embed_provider_id: str | None = None,
    embed_model_override: str | None = None,
) -> list[list[float]]:
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
        embed_model = rag_embed_model or _legacy_default_embed_model()
    
    try:
        return _invoke_runtime_embed(
            provider_id=resolved_provider_id,
            model=embed_model,
            texts=texts,
        )
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to get embeddings: {e}")
        raise


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
            qclient.recreate_collection(
                collection_name,
                vectors_config={
                    "dense": VectorParams(size=dim, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(),
                },
            )
            _WEBUI_LOG.info(
                f"Created Qdrant collection '{collection_name}' (dim={dim}, hybrid sparse)"
            )
        else:
            qclient.recreate_collection(
                collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            _WEBUI_LOG.info(f"Created Qdrant collection '{collection_name}' (dim={dim})")
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


def _snapshot_indexing_stats(st: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy for progress callbacks (skip_reasons copied so callers see fresh counts)."""
    snap = dict(st)
    snap["skip_reasons"] = dict(st.get("skip_reasons") or {})
    snap["errors"] = list(st.get("errors") or [])
    return snap


def _record_page_skip(st: dict[str, Any], reason: str, error_msg: str | None = None) -> None:
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
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Create a Qdrant collection by indexing pages from specified sources.
    Returns statistics about the indexing process.
    If on_progress is set, called as on_progress(processed_count, total_pages, stats) after each page.
    """
    sources_dir = _get_crawler_sources_dir()
    qdrant_url = get_qdrant_url().rstrip("/")
    qclient = QdrantClient(url=qdrant_url)
    
    stats: dict[str, Any] = {
        "total_pages": 0,
        "indexed_pages": 0,
        "total_chunks": 0,
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
    }

    hybrid_cfg = is_hybrid_sparse_enabled()
    effective_hybrid = False

    first_dim: int | None = None
    upsert_batch: list[PointStruct] = []
    BATCH_SIZE = 200
    
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
    
    stats["total_pages"] = len(candidates)
    
    if not candidates:
        return stats
    
    processed = 0
    total_pages = len(candidates)

    # Process each page
    for source_id, filename, entry, pages_dir, source_meta in candidates:
        if should_cancel and should_cancel():
            stats["cancelled"] = True
            stats["current_phase"] = "cancelled"
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            break

        page_path = os.path.join(pages_dir, filename)
        stats["current_source_id"] = source_id
        stats["current_filename"] = filename
        stats["current_phase"] = "reading"
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
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        prep = prepare_markdown_for_indexing(filename, md)
        if prep.skipped:
            _record_page_skip(
                stats,
                prep.skip_reason or "other",
                prep.skip_detail,
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        page_meta = prep.page_meta
        md = prep.body_md

        # Split into chunks
        stats["current_phase"] = "chunking"
        try:
            chunks_with_paths = split_markdown_into_chunks(
                md, max_chunk_size=chunk_max_size, min_chunk_size=chunk_min_size
            )
            chunks_with_paths = [(t, p) for t, p in chunks_with_paths if chunk_quality_ok(t)]
        except Exception as e:
            _record_page_skip(
                stats,
                "chunk_failed",
                f"Failed to chunk {source_id}/{filename}: {e}",
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        if not chunks_with_paths:
            _record_page_skip(stats, "no_valid_chunks")
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        embed_texts = [
            build_embed_prefix(page_meta, sp) + t
            for t, sp in chunks_with_paths
        ]

        # Get embeddings
        stats["current_phase"] = "embedding"
        if on_progress:
            on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
        try:
            embeddings = _get_embeddings_simple(
                embed_texts,
                embed_provider_id=embed_provider_id,
                embed_model_override=embed_model,
            )
        except Exception as e:
            _record_page_skip(
                stats,
                "embed_failed",
                f"Failed to get embeddings for {source_id}/{filename}: {e}",
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        if should_cancel and should_cancel():
            stats["cancelled"] = True
            stats["current_phase"] = "cancelled"
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            break

        if not embeddings:
            _record_page_skip(
                stats,
                "embed_failed",
                f"No embeddings returned for {source_id}/{filename}",
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        dim = len(embeddings[0])
        if first_dim is None:
            first_dim = dim
            _ensure_collection_with_name(
                qclient, collection_name, first_dim, hybrid_sparse=hybrid_cfg
            )
            effective_hybrid = hybrid_cfg and _qdrant_collection_has_sparse_vectors(
                qclient, collection_name
            )

        if dim != first_dim:
            _record_page_skip(
                stats,
                "dim_mismatch",
                f"Dimension mismatch for {source_id}/{filename}: {dim} != {first_dim}",
            )
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            continue

        stats["current_phase"] = "saving"
        if on_progress:
            on_progress(processed, total_pages, _snapshot_indexing_stats(stats))

        if should_cancel and should_cancel():
            stats["cancelled"] = True
            stats["current_phase"] = "cancelled"
            if on_progress:
                on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
            break
        
        # Create points
        url_for_meta = page_meta.get("url") or entry.get("url")
        for (chunk_text, section_path), vec in zip(chunks_with_paths, embeddings):
            section_path_str = ":".join(section_path) if section_path else ""
            chunk_hash = _sha256(f"{source_id}:{filename}:{section_path_str}:{chunk_text}")
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
            display_meta = infer_chunk_display_meta(section_path)
            section_path_joined = section_path_str  # same as hash segment; Qdrant filter helper
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
                        chunk_text, vec, hybrid_sparse=effective_hybrid
                    ),
                    payload=payload,
                )
            )
            
            stats["total_chunks"] += 1
        
        # Flush batch if needed
        if len(upsert_batch) >= BATCH_SIZE:
            try:
                qclient.upsert(collection_name=collection_name, points=upsert_batch)
                upsert_batch.clear()
            except Exception as e:
                stats["errors"].append(f"Failed to upsert batch: {e}")
        
        stats["indexed_pages"] += 1

        processed += 1
        stats["current_phase"] = "idle"
        if on_progress:
            on_progress(processed, total_pages, _snapshot_indexing_stats(stats))
    
    # Flush remaining batch
    if upsert_batch:
        try:
            qclient.upsert(collection_name=collection_name, points=upsert_batch)
        except Exception as e:
            stats["errors"].append(f"Failed to upsert final batch: {e}")
    
    return stats


@webui_bp.route("/crawler/sources", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_crawler_sources", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/sources/<source_id>", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_crawler_source", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/sources/<source_id>/pages", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_crawler_source_pages", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/indexer-tester/sources", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_indexer_tester_sources", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/indexer-tester/sources/<source_id>/files", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_indexer_tester_files", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/indexer-tester/sources/<source_id>/files/<path:filename>", methods=["GET"])
def get_indexer_tester_file_detail(source_id: str, filename: str) -> Any:
    """
    Return original and processed markdown for a specific page using WebUI/app.py pipeline.
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
        _ERROR_LOG.error("webui_routes.get_indexer_tester_file_detail", exc_info=True)
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
    ollama_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    options = {"temperature": 0.0}
    resolved_provider_id = str(provider_id or "").strip()
    if resolved_provider_id:
        return _invoke_runtime_chat(
            provider_id=resolved_provider_id,
            model=use_model,
            messages=ollama_messages,
            options=options,
        )
    return chat_client.chat(ollama_messages, use_model, stream=False, options=options) or ""


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

    webui_dir = os.path.join(_ROOT, "WebUI") if os.path.isdir(os.path.join(_ROOT, "WebUI")) else None
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


@webui_bp.route("/crawler/indexer-tester/evaluate", methods=["POST"])
@webui_bp.route("/crawler/indexer-tester/evaluate/", methods=["POST"])
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

        webui_dir = None
        possible_webui = os.path.join(_ROOT, "WebUI")
        if os.path.isdir(possible_webui):
            webui_dir = possible_webui
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
        _ERROR_LOG.error("webui_routes.indexer_tester_evaluate", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/indexer-tester/evaluate-batch", methods=["POST"])
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
        _ERROR_LOG.error("webui_routes.start_indexer_tester_evaluate_batch", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/indexer-tester/evaluate-batch/status/<job_id>", methods=["GET"])
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


@webui_bp.route("/crawler/indexer-tester/evaluate-batch/detect-patterns", methods=["POST"])
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

        webui_dir = os.path.join(_ROOT, "WebUI") if os.path.isdir(os.path.join(_ROOT, "WebUI")) else None
        collection_name = (_get_qdrant_collection_names() or [None])[0]
        params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
        chat_client = deps.chat_client
        use_model = model or (params.model_name if params else None)
        if not use_model:
            return _error_response("No chat model configured", 400)

        system_prompt = BATCH_PATTERNS_SYSTEM_PROMPT
        ollama_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options = {"temperature": 0.0}
        if provider_id:
            patterns = _invoke_runtime_chat(
                provider_id=provider_id,
                model=use_model,
                messages=ollama_messages,
                options=options,
            )
        else:
            patterns = chat_client.chat(ollama_messages, use_model, stream=False, options=options) or ""
        return jsonify({"patterns": (patterns or "").strip()})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.detect_batch_eval_patterns", exc_info=True)
        return _error_response(e)


# ---- MD Pipelines (config-driven markdown cleanup) ----

@webui_bp.route("/crawler/md-pipelines", methods=["GET"])
def get_md_pipelines_list() -> Any:
    """List available pipeline names (config/md_pipelines/*.json)."""
    if list_pipeline_names is None:
        return _error_response("md_indexer module not available", 500)
    try:
        names = list_pipeline_names()
        return jsonify({"pipelines": names})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_md_pipelines_list", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_md_pipeline", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["PUT", "POST"])
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
        _ERROR_LOG.error("webui_routes.save_md_pipeline", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["DELETE"])
def delete_md_pipeline(name: str) -> Any:
    """Delete pipeline by name."""
    if md_indexer_delete_pipeline is None:
        return _error_response("md_indexer module not available", 500)
    try:
        if md_indexer_delete_pipeline(name):
            return jsonify({"ok": True, "name": name})
        return _error_response(f"Pipeline '{name}' not found", 404)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_md_pipeline", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/md-pipelines/preview", methods=["POST"])
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
        _ERROR_LOG.error("webui_routes.preview_md_pipeline", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/sources/<source_id>/stats", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_crawler_source_stats", exc_info=True)
        return _error_response(e)


# Track crawling processes
_crawling_processes: dict[str, subprocess.Popen] = {}


def _get_webui_app_path() -> str:
    """Get path to WebUI/app.py."""
    possible_paths = [
        os.path.join(_ROOT, "WebUI", "app.py"),
        os.path.join(os.path.dirname(_ROOT), "WebUI", "app.py"),
    ]
    for path in possible_paths:
        if os.path.isfile(path):
            return path
    # Fallback
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(api_dir), "WebUI", "app.py")


@webui_bp.route("/crawler/sources/<source_id>/crawl", methods=["POST"])
def crawl_source_endpoint(source_id: str) -> Any:
    """Start crawling a specific source. Returns immediately, crawl runs in background."""
    try:
        # Check if source exists
        meta = _load_source_meta(source_id)
        if not meta:
            # Try to get source from SOURCES in WebUI/app.py
            app_path = _get_webui_app_path()
            if not os.path.isfile(app_path):
                return _error_response("WebUI/app.py not found", 500)
            
            # For now, we'll allow crawling even if meta doesn't exist
            # The crawl will create it
        
        # Check if already crawling
        if source_id in _crawling_processes:
            proc = _crawling_processes[source_id]
            if proc.poll() is None:  # Still running
                return jsonify({
                    "status": "already_running",
                    "message": f"Crawl for source '{source_id}' is already in progress"
                }), 409
        
        # Start crawl in background
        app_path = _get_webui_app_path()
        if not os.path.isfile(app_path):
            return _error_response("WebUI/app.py not found", 500)
        
        # Run crawl in subprocess
        env = os.environ.copy()
        env["CHIRONAI_PROJECT_ROOT"] = _ROOT
        env["CHIRONAI_WEBUI_DIR"] = os.path.join(_ROOT, "WebUI")
        _extra_path = os.pathsep.join(
            [
                _ROOT,
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
        _ERROR_LOG.error("webui_routes.crawl_source_endpoint", exc_info=True)
        return _error_response(e)


@webui_bp.route("/crawler/sources/<source_id>/crawl/status", methods=["GET"])
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
        _ERROR_LOG.error("webui_routes.get_crawl_status", exc_info=True)
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
                    _collection_jobs[job_id]["processed_pages"] = processed
                    _collection_jobs[job_id]["total_pages"] = total
                    _collection_jobs[job_id]["indexed_pages"] = st.get("indexed_pages", 0)
                    _collection_jobs[job_id]["total_chunks"] = st.get("total_chunks", 0)
                    _collection_jobs[job_id]["skipped_pages"] = st.get("skipped_pages", 0)
                    _collection_jobs[job_id]["errors"] = list(st.get("errors", [])[-8:])
                    sr = st.get("skip_reasons") or {}
                    _collection_jobs[job_id]["skip_reasons"] = dict(sr)
                    _collection_jobs[job_id]["current_source_id"] = st.get("current_source_id", "")
                    _collection_jobs[job_id]["current_filename"] = st.get("current_filename", "")
                    _collection_jobs[job_id]["current_phase"] = st.get("current_phase", "")
                    _collection_jobs[job_id]["last_skip_reason"] = st.get("last_skip_reason", "")
                    _collection_jobs[job_id]["cancelled"] = bool(st.get("cancelled", False))

        try:
            stats = _create_collection_from_sources(
                collection_name=collection_name,
                source_ids=source_ids,
                chunk_max_size=chunk_max_size,
                chunk_min_size=chunk_min_size,
                on_progress=on_progress,
                embed_provider_id=embed_provider_id,
                embed_model=embed_model,
                should_cancel=should_cancel,
            )
            with _collection_jobs_lock:
                if job_id in _collection_jobs:
                    cancelled = bool(stats.get("cancelled")) or bool(_collection_jobs[job_id].get("cancel_requested"))
                    _collection_jobs[job_id]["status"] = "cancelled" if cancelled else "success"
                    _collection_jobs[job_id]["statistics"] = stats
                    _collection_jobs[job_id]["processed_pages"] = (
                        _collection_jobs[job_id].get("processed_pages", 0)
                        if cancelled
                        else stats.get("total_pages", 0)
                    )
                    _collection_jobs[job_id]["indexed_pages"] = stats.get("indexed_pages", 0)
                    _collection_jobs[job_id]["total_chunks"] = stats.get("total_chunks", 0)
                    _collection_jobs[job_id]["skipped_pages"] = stats.get("skipped_pages", 0)
                    _collection_jobs[job_id]["skip_reasons"] = dict(stats.get("skip_reasons") or {})
                    _collection_jobs[job_id]["current_phase"] = "cancelled" if cancelled else "complete"
                    _collection_jobs[job_id]["current_source_id"] = ""
                    _collection_jobs[job_id]["current_filename"] = ""
                    _collection_jobs[job_id]["cancelled"] = cancelled
        except Exception as e:
            _ERROR_LOG.error("webui_routes.create_collection job", exc_info=True)
            with _collection_jobs_lock:
                if job_id in _collection_jobs:
                    _collection_jobs[job_id]["status"] = "failed"
                    _collection_jobs[job_id]["error"] = str(e)


@webui_bp.route("/crawler/create-collection-status/<job_id>", methods=["GET"])
def get_create_collection_status(job_id: str) -> Any:
    """Return progress or result of a create-collection job."""
    with _collection_jobs_lock:
        job = _collection_jobs.get(job_id)
    if not job:
        return _error_response("Job not found", 404, extra={"job_id": job_id})
    return jsonify({
        "job_id": job_id,
        "status": job.get("status", "running"),
        "collection_name": job.get("collection_name", ""),
        "source_ids": job.get("source_ids", []),
        "processed_pages": job.get("processed_pages", 0),
        "total_pages": job.get("total_pages", 0),
        "indexed_pages": job.get("indexed_pages", 0),
        "total_chunks": job.get("total_chunks", 0),
        "skipped_pages": job.get("skipped_pages", 0),
        "skip_reasons": job.get("skip_reasons", {}),
        "current_source_id": job.get("current_source_id", ""),
        "current_filename": job.get("current_filename", ""),
        "current_phase": job.get("current_phase", ""),
        "last_skip_reason": job.get("last_skip_reason", ""),
        "cancel_requested": bool(job.get("cancel_requested", False)),
        "cancelled": bool(job.get("cancelled", False)),
        "errors": job.get("errors", []),
        "statistics": job.get("statistics"),
        "error": job.get("error"),
    })


@webui_bp.route("/crawler/create-collection-cancel/<job_id>", methods=["POST"])
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
    return jsonify({
        "job_id": job_id,
        "status": "running",
        "cancel_requested": True,
    })


@webui_bp.route("/crawler/create-collection", methods=["POST"])
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

        if not collection_name:
            return _error_response("collection_name is required", 400)

        if not source_ids:
            return _error_response("At least one source_id is required", 400)

        if not is_safe_identifier(collection_name):
            return _error_response("Collection name must contain only alphanumeric characters, underscores, and hyphens", 400)

        qdrant_url = get_qdrant_url().rstrip("/")
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
            _collection_jobs[job_id] = {
                "status": "running",
                "collection_name": collection_name,
                "source_ids": list(available_sources),
                "processed_pages": 0,
                "total_pages": total_pages,
                "indexed_pages": 0,
                "total_chunks": 0,
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
                "cancel_requested": False,
                "cancelled": False,
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
        _ERROR_LOG.error("webui_routes.create_collection", exc_info=True)
        return _error_response(e)

__all__ = ["webui_bp"]
