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
import sysconfig
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

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

from application.llm_proxy_builds import (
    LLM_PROXY_BUILDS_APP_KEY,
    diagnose_build,
    dump_builds_json,
    extract_context_length_from_show,
    find_build_by_id,
    load_builds_json,
    validate_builds_list,
)
from application.rag.collection_freshness import check_collection_freshness
from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_hybrid_sparse_enabled,
    resolve_web_interaction_flags,
)
from application.rag.params import get_rag_answer_params

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
    get_build_proxy_port,
    get_default_rag_top_k,
    get_framework_collection_ttl_days,
    get_ollama_chat_model,
    get_ollama_embed_model,
    get_ollama_rerank_model,
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
    list_rag_prompt_names,
    rag_prompt_file_exists,
    PROMPTS_DIR,
)

# Trash directory for deleted prompts
TRASH_DIR = PROMPTS_DIR / ".trash"


def is_readme_name(name: str) -> bool:
    """Check if a prompt name is README (case-insensitive)."""
    return name.lower() == "readme"
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
    get_rag_test_runs_repository,
)
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from api.http.webui_session import log_to_database
from api.http.proxy_status import (
    set_proxy_status,
    set_latest_request_seconds,
    set_latest_request_total_tokens,
    set_latest_request_rag_steps,
    get_proxy_status_label,
    get_latest_request_seconds,
    get_latest_request_total_tokens,
    get_latest_request_rag_steps,
    STATUS_IDLE,
    STATUS_RAG_SEARCH,
    STATUS_PREPARING_RESPONSE,
    STATUS_RESPONSE,
)
from api.http.proxy_trace import (
    annotate_proxy_trace_for_ui,
    clear_proxy_trace_buffer,
    get_current_trace,
    get_current_trace_updated_at,
    recent_proxy_traces,
)
from api.http.service_control import (
    get_open_webui_config,
    open_webui_status_snapshot,
    start_ollama as start_ollama_service,
    start_open_webui as start_open_webui_service,
    start_qdrant as start_qdrant_service,
    stop_ollama as stop_ollama_service,
    stop_open_webui as stop_open_webui_service,
    stop_qdrant as stop_qdrant_service,
)

import requests

from infrastructure.ollama.cli_runner import (
    OllamaInteractorCliError,
    invoke_delete,
    invoke_embed,
    invoke_ping,
    invoke_show,
    invoke_tags,
    iter_pull_objects,
)
from infrastructure.ollama.ollama_model_visibility import (
    filter_ollama_tag_entries_for_editors,
    get_hidden_ollama_model_ids,
    patch_hidden_ollama_model_ids,
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

# Import config for embeddings
try:
    from config import get_ollama_embed_url
except ImportError:
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore

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
import re
import subprocess
try:
    import winreg  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - non-Windows fallback
    winreg = None  # type: ignore[assignment]

# In-memory buffer for dev console (last 50 requests)
_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

webui_bp = Blueprint("webui", __name__, url_prefix=WEBUI_URL_PREFIX)

# Persisted Open WebUI → backend (Ollama-compatible base URL, e.g. LLM Proxy).
OPEN_WEBUI_OLLAMA_BASE_URL_APP_KEY = "open_webui_ollama_base_url"


def _normalize_open_webui_ollama_base_url(raw: str) -> str:
    """Return canonical http(s)://host[:port] with no path or trailing slash."""
    s = (raw or "").strip().rstrip("/")
    if not s:
        raise ValueError("URL is empty")
    if "://" not in s:
        s = f"http://{s}"
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must include a host")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}".rstrip("/")

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


def _run_unified_proxy_chat(body: dict[str, Any]) -> Any:
    """Delegate chat handling to /v1 chat_completions core to avoid duplicate RAG logic."""
    wiring = current_app.extensions.get("llm_proxy_wiring")
    if wiring is None:
        return jsonify({"error": "LLM proxy wiring not initialized"}), 500
    from llm_proxy.chat_completions import run_chat_completions

    return run_chat_completions(wiring, body_override=body)



@webui_bp.route("/models", methods=["GET"])
def get_models() -> Any:
    """Return list of available models from Ollama."""
    try:
        ollama_url = _get_ollama_url()
        models_list = []
        
        # Ollama model list: OllamaInteractor ollama_http.get_tags (in-process), CLI fallback
        try:
            data = invoke_tags(base_url=ollama_url.rstrip("/"), timeout=5.0)
            raw_models = [m for m in (data.get("models") or []) if isinstance(m, dict)]
            ollama_models = filter_ollama_tag_entries_for_editors(
                raw_models,
                get_hidden_ollama_model_ids(),
            )
            for model in ollama_models:
                model_name = (model.get("name") or model.get("model") or "").strip()
                if model_name:
                    models_list.append({
                        "id": model_name,
                        "name": model_name,
                        "description": f"Ollama model: {model_name}",
                        "size": model.get("size", 0),
                        "modified_at": model.get("modified_at", ""),
                    })
        except Exception as e:
            _WEBUI_LOG.warning(f"Failed to fetch Ollama models: {e}")
            # Fallback to config model if Ollama is not available
            model_name = get_ollama_chat_model()
            models_list.append({
                "id": model_name,
                "name": model_name,
                "description": f"Ollama chat model: {model_name} (from config)",
            })

        try:
            settings_repo = get_settings_repository()
            if (settings_repo.get_app_setting("proxy_autocomplete_model") or "").strip():
                models_list.insert(0, {
                    "id": AUTOCOMPLETE_MODEL_ID,
                    "name": AUTOCOMPLETE_MODEL_ID,
                    "description": "Autocomplete (maps to LLM Proxy → Autocomplete Ollama model)",
                })
        except Exception:
            pass

        return jsonify({"models": models_list})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_models", exc_info=True)
        log_to_database("ERROR", str(e), source="webui_routes.get_models", error_type=type(e).__name__)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts", methods=["GET"])
def get_prompts() -> Any:
    """Return list of available prompt names."""
    try:
        names = list_rag_prompt_names()
        return jsonify({
            "prompts": [{"name": name, "id": name} for name in names],
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_prompts", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/<name>", methods=["GET"])
def get_prompt_content(name: str) -> Any:
    """Get content of a specific prompt file."""
    try:
        if ".." in name or "/" in name or "\\" in name:
            return jsonify({"error": "Invalid prompt name"}), 400
        
        path = PROMPTS_DIR / f"{name}.md"
        if not path.is_file():
            return jsonify({"error": "Prompt not found"}), 404
        
        content = path.read_text(encoding="utf-8")
        return jsonify({
            "name": name,
            "content": content,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_prompt_content", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts", methods=["POST"])
def create_prompt() -> Any:
    """Create a new prompt or duplicate an existing one."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        source_name = body.get("source_name")
        name = body.get("name")
        content = body.get("content")
        
        if not name:
            return jsonify({"error": "name is required"}), 400
        
        if ".." in name or "/" in name or "\\" in name:
            return jsonify({"error": "Invalid prompt name"}), 400
        
        # Prevent creating files named README
        if is_readme_name(name):
            return jsonify({"error": "Cannot create a file named README"}), 403
        
        path = PROMPTS_DIR / f"{name}.md"
        if path.exists():
            return jsonify({"error": "Prompt already exists"}), 409
        
        # If duplicating, load source content
        if source_name and not content:
            if ".." in source_name or "/" in source_name or "\\" in source_name:
                return jsonify({"error": "Invalid source prompt name"}), 400
            source_path = PROMPTS_DIR / f"{source_name}.md"
            if not source_path.is_file():
                return jsonify({"error": "Source prompt not found"}), 404
            content = source_path.read_text(encoding="utf-8")
        
        if not content:
            return jsonify({"error": "content is required"}), 400
        
        # Ensure prompts directory exists
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        
        path.write_text(content, encoding="utf-8")
        return jsonify({
            "name": name,
            "status": "created",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.create_prompt", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/<name>", methods=["PUT"])
def update_prompt(name: str) -> Any:
    """Update prompt content and/or rename it."""
    try:
        if ".." in name or "/" in name or "\\" in name:
            return jsonify({"error": "Invalid prompt name"}), 400
        
        body = request.get_json(force=True, silent=True) or {}
        new_name = body.get("new_name")
        content = body.get("content")
        
        path = PROMPTS_DIR / f"{name}.md"
        if not path.is_file():
            return jsonify({"error": "Prompt not found"}), 404
        
        # Prevent editing README
        if is_readme_name(name):
            return jsonify({"error": "README cannot be edited"}), 403
        
        # Handle rename
        if new_name and new_name != name:
            if ".." in new_name or "/" in new_name or "\\" in new_name:
                return jsonify({"error": "Invalid new prompt name"}), 400
            
            # Prevent renaming to README
            if is_readme_name(new_name):
                return jsonify({"error": "Cannot rename to README"}), 403
            
            new_path = PROMPTS_DIR / f"{new_name}.md"
            if new_path.exists():
                return jsonify({"error": "New prompt name already exists"}), 409
            
            # If content is provided, write to new file; otherwise move
            if content is not None:
                new_path.write_text(content, encoding="utf-8")
                path.unlink()
            else:
                path.rename(new_path)
            return jsonify({
                "name": new_name,
                "status": "renamed",
            })
        
        # Handle content update
        if content is not None:
            path.write_text(content, encoding="utf-8")
            return jsonify({
                "name": name,
                "status": "updated",
            })
        
        return jsonify({"error": "No changes specified"}), 400
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_prompt", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/<name>", methods=["DELETE"])
def delete_prompt(name: str) -> Any:
    """Move a prompt file to trash instead of deleting permanently."""
    try:
        if ".." in name or "/" in name or "\\" in name:
            return jsonify({"error": "Invalid prompt name"}), 400
        
        # Prevent deleting README
        if is_readme_name(name):
            return jsonify({"error": "README cannot be deleted"}), 403
        
        path = PROMPTS_DIR / f"{name}.md"
        if not path.is_file():
            return jsonify({"error": "Prompt not found"}), 404
        
        # Ensure trash directory exists
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        
        # Move to trash
        trash_path = TRASH_DIR / f"{name}.md"
        # If file already exists in trash, add timestamp
        if trash_path.exists():
            import time
            timestamp = int(time.time())
            trash_path = TRASH_DIR / f"{name}.{timestamp}.md"
        
        path.rename(trash_path)
        return jsonify({
            "name": name,
            "status": "moved_to_trash",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_prompt", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/trash", methods=["GET"])
def get_trash_prompts() -> Any:
    """Get list of prompts in trash."""
    try:
        if not TRASH_DIR.is_dir():
            return jsonify({"prompts": []})
        
        prompts = []
        for path in TRASH_DIR.iterdir():
            if path.suffix.lower() == ".md" and path.name[0] != ".":
                # Extract original name (remove timestamp if present)
                name = path.stem
                if "." in name:
                    # Try to extract original name before timestamp
                    parts = name.rsplit(".", 1)
                    if parts[1].isdigit():
                        name = parts[0]
                prompts.append({
                    "name": name,
                    "trash_name": path.name,
                    "trash_path": str(path.relative_to(TRASH_DIR)),
                })
        
        return jsonify({"prompts": sorted(prompts, key=lambda x: x["name"])})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_trash_prompts", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/trash/<trash_name>", methods=["GET"])
def get_trash_prompt_content(trash_name: str) -> Any:
    """Get content of a prompt file from trash."""
    try:
        if ".." in trash_name or "/" in trash_name or "\\" in trash_name:
            return jsonify({"error": "Invalid trash name"}), 400
        
        trash_path = TRASH_DIR / trash_name
        if not trash_path.is_file():
            return jsonify({"error": "Prompt not found in trash"}), 404
        
        content = trash_path.read_text(encoding="utf-8")
        
        # Extract original name
        name = trash_path.stem
        if "." in name:
            parts = name.rsplit(".", 1)
            if parts[1].isdigit():
                name = parts[0]
        
        return jsonify({
            "name": name,
            "trash_name": trash_name,
            "content": content,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_trash_prompt_content", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/trash/<trash_name>", methods=["PUT"])
def update_trash_prompt(trash_name: str) -> Any:
    """Update content of a prompt file in trash."""
    try:
        if ".." in trash_name or "/" in trash_name or "\\" in trash_name:
            return jsonify({"error": "Invalid trash name"}), 400
        
        body = request.get_json(force=True, silent=True) or {}
        content = body.get("content")
        
        if content is None:
            return jsonify({"error": "content is required"}), 400
        
        trash_path = TRASH_DIR / trash_name
        if not trash_path.is_file():
            return jsonify({"error": "Prompt not found in trash"}), 404
        
        trash_path.write_text(content, encoding="utf-8")
        
        # Extract original name
        name = trash_path.stem
        if "." in name:
            parts = name.rsplit(".", 1)
            if parts[1].isdigit():
                name = parts[0]
        
        return jsonify({
            "name": name,
            "trash_name": trash_name,
            "status": "updated",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_trash_prompt", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/trash/<trash_name>/restore", methods=["POST"])
def restore_prompt(trash_name: str) -> Any:
    """Restore a prompt from trash."""
    try:
        if ".." in trash_name or "/" in trash_name or "\\" in trash_name:
            return jsonify({"error": "Invalid trash name"}), 400
        
        trash_path = TRASH_DIR / trash_name
        if not trash_path.is_file():
            return jsonify({"error": "Prompt not found in trash"}), 404
        
        # Extract original name
        name = trash_path.stem
        if "." in name:
            parts = name.rsplit(".", 1)
            if parts[1].isdigit():
                name = parts[0]
        
        restore_path = PROMPTS_DIR / f"{name}.md"
        if restore_path.exists():
            return jsonify({"error": "A prompt with this name already exists"}), 409
        
        # Move back from trash
        trash_path.rename(restore_path)
        return jsonify({
            "name": name,
            "status": "restored",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.restore_prompt", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/prompts/trash", methods=["DELETE"])
def clear_trash() -> Any:
    """Permanently delete all prompts from trash."""
    try:
        if not TRASH_DIR.is_dir():
            return jsonify({"status": "cleared", "deleted_count": 0})
        
        deleted_count = 0
        for path in TRASH_DIR.iterdir():
            if path.suffix.lower() == ".md" and path.name[0] != ".":
                path.unlink()
                deleted_count += 1
        
        return jsonify({
            "status": "cleared",
            "deleted_count": deleted_count,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.clear_trash", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/config", methods=["GET"])
def get_config() -> Any:
    """Return current RAG configuration."""
    try:
        return jsonify({
            "context_chunk_chars": get_rag_int("context_chunk_chars", 1000),
            "context_total_chars": get_rag_int("context_total_chars", 7000),
            "top_k": get_rag_int("top_k", 4),
            "confidence_threshold": get_rag_float("confidence_threshold", 0.75),
            "model_name": get_ollama_chat_model(),
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_config", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/logs", methods=["GET"])
def get_logs() -> Any:
    """Return recent log entries from database."""
    try:
        session_id = request.args.get("session_id")
        limit = int(request.args.get("limit", 100))
        level = request.args.get("level", "").upper() or None
        source = request.args.get("source") or None
        since_id = request.args.get("since_id")
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id=session_id,
            level=level,
            limit=limit,
            since_id=int(since_id) if since_id else None,
            source=source,
        )
        
        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_logs", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/notifications", methods=["GET"])
def get_coreui_notifications() -> Any:
    """List CoreUI notification center entries for a session."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
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
        return jsonify({"error": str(e)}), 500


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
            return jsonify({"error": "session_id is required"}), 400
        if kind not in ("error", "event", "info"):
            return jsonify({"error": "kind must be error, event, or info"}), 400
        if not source:
            return jsonify({"error": "source is required"}), 400
        if not title:
            return jsonify({"error": "title is required"}), 400
        if not isinstance(message, str):
            message = str(message)
        if len(message) > 8000:
            message = message[:8000] + "…"
        meta_dict: dict[str, Any] | None = None
        if metadata is not None:
            if not isinstance(metadata, dict):
                return jsonify({"error": "metadata must be an object"}), 400
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/notifications/<int:nid>/dismiss", methods=["PATCH"])
def dismiss_coreui_notification(nid: int) -> Any:
    """Mark a notification as dismissed."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id") or request.args.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        repo = get_notifications_repository()
        ok = repo.dismiss(session_id, nid)
        if not ok and session_id != "system":
            ok = repo.dismiss("system", nid)
        if not ok:
            return jsonify({"error": "not found or already dismissed"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.dismiss_coreui_notification", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/notifications/clear", methods=["POST"])
def clear_coreui_notifications() -> Any:
    """Remove all persisted notifications for the session (live activities unaffected)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        deleted = get_notifications_repository().clear_session(session_id)
        return jsonify({"deleted": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.clear_coreui_notifications", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-logs", methods=["GET"])
def get_proxy_logs() -> Any:
    """Return proxy logs from database (``session_id=proxy``, ``source=proxy``).

    ``since_id`` (max id from the previous poll) and ``limit`` apply in insertion order.
    """
    try:
        limit = int(request.args.get("limit", 100))
        since_id = request.args.get("since_id")
        from_date = request.args.get("from")
        to_date = request.args.get("to")
        ac_raw = (request.args.get("autocomplete_only") or "").strip().lower()
        autocomplete_only = ac_raw in ("1", "true", "yes")

        logs_repo = get_logs_repository()
        sid = int(since_id) if since_id else None
        if autocomplete_only:
            logs = logs_repo.get_logs(
                session_id="proxy",
                level="INFO",
                limit=limit,
                since_id=sid,
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
                since_id=sid,
                source="proxy",
                include_system=False,
                from_date=from_date or None,
                to_date=to_date or None,
            )

        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_logs", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-trace/current", methods=["GET"])
def get_proxy_trace_current() -> Any:
    """Return the latest live trace from in-memory store."""
    try:
        trace = get_current_trace()
        updated_at = get_current_trace_updated_at()
        return jsonify(
            {
                "trace": trace,
                "status": get_proxy_status_label(),
                "updated_at": updated_at,
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_trace_current", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-traces/clear", methods=["POST"])
def post_proxy_traces_clear() -> Any:
    try:
        clear_proxy_trace_buffer()
        return jsonify({"ok": True})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.post_proxy_traces_clear", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
            return jsonify({"error": "session_id and message are required"}), 400
        
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/logs", methods=["DELETE"])
def delete_logs() -> Any:
    """Delete log entries for a session from the database (matches GET scope by default)."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        inc_raw = (request.args.get("include_system") or "1").strip().lower()
        include_system = inc_raw not in ("0", "false", "no")

        logs_repo = get_logs_repository()
        deleted = logs_repo.delete_logs_for_session(
            session_id, include_system=include_system
        )
        return jsonify({"status": "ok", "deleted_count": deleted})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_logs", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
            return jsonify({"error": "messages is required"}), 400

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
        return jsonify({"error": str(e)}), 500
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/model-settings", methods=["GET"])
def get_model_settings() -> Any:
    """Get current model settings."""
    try:
        settings_repo = get_settings_repository()

        stored_model = (settings_repo.get_app_setting("proxy_model") or "").strip()
        stored_settings_json = settings_repo.get_app_setting("proxy_settings")
        stored_rag_col = (settings_repo.get_app_setting(RAG_COLLECTION_APP_SETTING) or "").strip()
        stored_autocomplete = (settings_repo.get_app_setting("proxy_autocomplete_model") or "").strip()

        out: dict[str, Any] = {
            "model": stored_model,
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/model-settings", methods=["POST"])
def update_model_settings() -> Any:
    """Update model settings (persisted to app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        if body.get("model") is not None:
            settings_repo.set_app_setting("proxy_model", str(body["model"]))
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
        merged = {**existing_blob, **body}
        settings_repo.set_app_setting("proxy_settings", json.dumps(merged))
        return jsonify({"status": "ok", "settings": merged})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_model_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
    ollama_names = _ollama_tag_name_set_for_builds_diag()
    qset = _get_cached_qdrant_collection_name_set_for_builds_diag()
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


@webui_bp.route("/llm-proxy/builds", methods=["GET"])
def get_llm_proxy_builds() -> Any:
    """List LLM Proxy builds with validation hints for WebUI."""
    try:
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        builds = load_builds_json(raw)
        enriched = _enrich_builds_with_diagnostics(builds)
        sh = get_server_host()
        dh = "127.0.0.1" if sh in ("0.0.0.0", "::", "") else sh
        bp_port = get_build_proxy_port()
        main_port = get_server_port()
        return jsonify(
            {
                "builds": enriched,
                "openai_models_urls": {
                    "main": f"http://{dh}:{main_port}/v1/models",
                    "build_proxy": f"http://{dh}:{bp_port}/v1/models",
                },
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_llm_proxy_builds", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/llm-proxy/builds", methods=["PUT"])
def put_llm_proxy_builds() -> Any:
    """Replace full builds list (atomic validation)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw_list = body.get("builds")
        if not isinstance(raw_list, list):
            return jsonify({"error": "builds must be a JSON array"}), 400
        normalized, errs = validate_builds_list([x for x in raw_list if isinstance(x, dict)])
        if normalized is None:
            return jsonify({"error": "validation failed", "details": errs}), 400
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting(LLM_PROXY_BUILDS_APP_KEY, dump_builds_json(normalized))
        enriched = _enrich_builds_with_diagnostics(normalized)
        return jsonify({"ok": True, "builds": enriched})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.put_llm_proxy_builds", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/llm-proxy/builds/<build_id>", methods=["GET"])
def get_llm_proxy_build_one(build_id: str) -> Any:
    """Single build by id with diagnostics."""
    try:
        if ".." in build_id or "/" in build_id or "\\" in build_id:
            return jsonify({"error": "Invalid id"}), 400
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
        builds = load_builds_json(raw)
        b = find_build_by_id(builds, build_id)
        if not b:
            return jsonify({"error": "not found"}), 404
        enriched = _enrich_builds_with_diagnostics([b])[0]
        return jsonify({"build": enriched})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_llm_proxy_build_one", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/llm-proxy/builds/preview-model", methods=["POST"])
def llm_proxy_build_preview_model() -> Any:
    """Ollama show: context_length + thinking support for form helpers."""
    body = request.get_json(force=True, silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model is required"}), 400
    url = _get_ollama_url().rstrip("/")
    try:
        details = invoke_show(base_url=url, name=model, timeout=60.0)
    except OllamaInteractorCliError as e:
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


@webui_bp.route("/proxy-configured/status", methods=["GET"])
def get_proxy_configured_status() -> Any:
    """Check if proxy configured script files exist."""
    try:
        claude_script = Path(_ROOT) / "start_claude_proxy_configured.ps1"
        codex_script = Path(_ROOT) / "start_codex_proxy_configured.ps1"
        return jsonify({
            "claude_exists": claude_script.is_file(),
            "codex_exists": codex_script.is_file(),
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_configured_status", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _norm_path_for_compare(p: str) -> str:
    return os.path.normcase(os.path.normpath((p or "").strip().rstrip("\\/")))


def _split_path_entries(path_value: str) -> list[str]:
    return [x.strip() for x in (path_value or "").split(";") if x and x.strip()]


def _get_chiron_shim_dir() -> str:
    return str((Path.home() / ".chironai" / "bin").resolve())


def _get_chiron_codex_shim_path() -> str:
    return str((Path(_get_chiron_shim_dir()) / "codex.cmd").resolve())


def _get_windows_user_path() -> str:
    if os.name != "nt" or winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            val, _ = winreg.QueryValueEx(key, "Path")
            return str(val or "")
    except Exception:
        return ""


def _set_windows_user_path(entries: list[str]) -> bool:
    if os.name != "nt" or winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            new_path = ";".join(entries)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            return True
    except Exception:
        return False


def _update_path_entries(entries: list[str], target: str, *, prepend: bool) -> tuple[list[str], bool]:
    target_clean = (target or "").strip()
    if not target_clean:
        return entries, False
    target_norm = _norm_path_for_compare(target_clean)
    idx = -1
    for i, entry in enumerate(entries):
        if _norm_path_for_compare(entry) == target_norm:
            idx = i
            break
    if idx >= 0:
        if prepend and idx != 0:
            out = entries[:]
            item = out.pop(idx)
            out.insert(0, item)
            return out, True
        return entries, False
    out = entries[:]
    if prepend:
        out.insert(0, target_clean)
    else:
        out.append(target_clean)
    return out, True


def _ensure_windows_user_path_entry(entry: str, *, prepend: bool = False) -> bool:
    if os.name != "nt" or winreg is None:
        return False
    target = (entry or "").strip()
    if not target:
        return False
    try:
        existing = _get_windows_user_path()
        entries = _split_path_entries(existing)
        updated, changed = _update_path_entries(entries, target, prepend=prepend)
        if not changed:
            return False
        return _set_windows_user_path(updated)
    except Exception:
        return False


def _build_status_cmd_env() -> dict[str, str] | None:
    """
    Build env for status checks that reflects latest User PATH from registry.
    This avoids stale PATH values from a long-running backend process.
    """
    if os.name != "nt":
        return None
    user_path = _get_windows_user_path().strip()
    if not user_path:
        return None
    env = os.environ.copy()
    existing = env.get("Path") or env.get("PATH") or ""
    merged = ";".join([p for p in [user_path, existing] if p])
    env["Path"] = merged
    env["PATH"] = merged
    return env


def _run_cmd_where(binary_name: str, env: dict[str, str] | None = None) -> tuple[list[str], str]:
    try:
        res = subprocess.run(
            ["cmd", "/c", "where", binary_name],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if res.returncode == 0:
            hits = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
            return hits, ""
        return [], (res.stderr or res.stdout or "").strip()
    except Exception as e:
        return [], str(e)


def _compute_global_status_diagnostics() -> dict[str, Any]:
    shim_dir = _get_chiron_shim_dir()
    shim_codex = _get_chiron_codex_shim_path()
    user_scripts_dir = ""
    try:
        if os.name == "nt":
            user_scripts_dir = str(Path(sysconfig.get_path("scripts", scheme="nt_user")).resolve())
    except Exception:
        user_scripts_dir = ""

    user_path = _get_windows_user_path()
    user_path_entries = _split_path_entries(user_path)
    user_path_has_shim_dir = any(
        _norm_path_for_compare(x) == _norm_path_for_compare(shim_dir) for x in user_path_entries
    )
    user_path_has_scripts_dir = any(
        _norm_path_for_compare(x) == _norm_path_for_compare(user_scripts_dir) for x in user_path_entries
    ) if user_scripts_dir else False
    user_path_shim_is_first = bool(user_path_entries) and (
        _norm_path_for_compare(user_path_entries[0]) == _norm_path_for_compare(shim_dir)
    )

    status_env = _build_status_cmd_env()
    codex_where_hits, codex_where_error = _run_cmd_where("codex", env=status_env)
    codex_first_hit = codex_where_hits[0] if codex_where_hits else ""
    codex_first_is_shim = bool(codex_first_hit) and (
        _norm_path_for_compare(codex_first_hit) == _norm_path_for_compare(shim_codex)
    )
    codex_shim_exists = Path(shim_codex).is_file()

    chironai_where_hits, chironai_where_error = _run_cmd_where("chironai", env=status_env)
    chironai_exists = len(chironai_where_hits) > 0

    launch_codex_available = False
    launch_error = ""
    if chironai_exists:
        try:
            launch_res = subprocess.run(
                ["cmd", "/c", "chironai", "launch", "codex", "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                env=status_env,
            )
            launch_codex_available = launch_res.returncode == 0
            if not launch_codex_available:
                launch_error = (launch_res.stderr or launch_res.stdout or "").strip()
        except Exception as e:
            launch_error = str(e)

    mismatch_reasons: list[str] = []
    if not codex_shim_exists:
        mismatch_reasons.append(f"shim missing: {shim_codex}")
    if not user_path_has_shim_dir:
        mismatch_reasons.append(f"user PATH missing shim dir: {shim_dir}")
    if user_path_has_shim_dir and not user_path_shim_is_first:
        mismatch_reasons.append(f"shim dir not first in user PATH: {shim_dir}")
    if codex_where_hits and not codex_first_is_shim:
        mismatch_reasons.append(f"PATH precedence wrong: where codex first hit is {codex_first_hit}")
    if not codex_where_hits and codex_where_error:
        mismatch_reasons.append(f"where codex failed: {codex_where_error}")
    if not chironai_exists:
        mismatch_reasons.append("chironai command not found in CMD PATH")
    if not launch_codex_available and launch_error:
        mismatch_reasons.append(f"`chironai launch codex --help` failed: {launch_error}")

    is_global = bool(codex_first_is_shim and chironai_exists and launch_codex_available)
    actionable_hint = ""
    if not is_global:
        if not codex_shim_exists:
            actionable_hint = "Click 'Install Chiron global' to create codex shim."
        elif codex_where_hits and not codex_first_is_shim:
            actionable_hint = "Shim exists but PATH precedence is wrong; re-run install to re-prepend shim dir."
        elif not chironai_exists:
            actionable_hint = "chironai is not visible in CMD PATH; re-run install and open a new CMD window."
        else:
            actionable_hint = "Run install and open a new CMD window, then click Re-check."

    return {
        "is_global": is_global,
        "shim_dir": shim_dir,
        "shim_codex_path": shim_codex,
        "codex_shim_exists": bool(codex_shim_exists),
        "codex_first_is_shim": bool(codex_first_is_shim),
        "codex_first_hit": codex_first_hit,
        "codex_where_hits": codex_where_hits,
        "codex_where_error": codex_where_error,
        "chironai_exists": bool(chironai_exists),
        "chironai_where_hits": chironai_where_hits,
        "chironai_where_error": chironai_where_error,
        "launch_codex_available": bool(launch_codex_available),
        "launch_error": launch_error,
        "user_scripts_dir": user_scripts_dir,
        "user_path_has_scripts_dir": bool(user_path_has_scripts_dir),
        "user_path_has_shim_dir": bool(user_path_has_shim_dir),
        "user_path_shim_is_first": bool(user_path_shim_is_first),
        "mismatch_reasons": mismatch_reasons,
        "actionable_hint": actionable_hint,
        "status_path_includes_user_path": bool(status_env is not None),
    }


def _detect_chiron_global_status() -> dict[str, Any]:
    return _compute_global_status_diagnostics()


@webui_bp.route("/proxy-configured/chiron-global/status", methods=["GET"])
def get_chiron_global_status() -> Any:
    """Check real global availability of `chironai launch codex` from CMD (not project-local flags)."""
    try:
        return jsonify(_detect_chiron_global_status())
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_chiron_global_status", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-configured/chiron-global/install", methods=["POST"])
def install_chiron_global() -> Any:
    """Install chironai CLI globally and ensure user PATH contains the Python user Scripts dir."""
    try:
        pip_cmd = [sys.executable, "-m", "pip", "install", "-e", _ROOT]
        pip_result = subprocess.run(
            pip_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if pip_result.returncode != 0:
            return jsonify(
                {
                    "error": "Failed to install chironai via pip",
                    "pip_returncode": pip_result.returncode,
                    "pip_stderr_tail": (pip_result.stderr or "")[-4000:],
                    "pip_stdout_tail": (pip_result.stdout or "")[-4000:],
                }
            ), 500

        path_updated = False
        shim_path_updated = False
        scripts_path_updated = False
        user_scripts_dir = ""
        shim_dir = _get_chiron_shim_dir()
        shim_codex = _get_chiron_codex_shim_path()
        shim_written = False

        # Create/update codex shim (global entrypoint in CMD).
        try:
            Path(shim_dir).mkdir(parents=True, exist_ok=True)
            shim_content = (
                "@echo off\r\n"
                "chironai launch codex --cd \"%CD%\" %*\r\n"
            )
            Path(shim_codex).write_text(shim_content, encoding="utf-8")
            shim_written = True
        except Exception:
            shim_written = False

        if os.name == "nt":
            try:
                user_scripts_dir = str(Path(sysconfig.get_path("scripts", scheme="nt_user")).resolve())
                shim_path_updated = _ensure_windows_user_path_entry(shim_dir, prepend=True)
                if user_scripts_dir:
                    scripts_path_updated = _ensure_windows_user_path_entry(user_scripts_dir, prepend=False)
                path_updated = bool(shim_path_updated or scripts_path_updated)
                # Refresh current process PATH so immediate status checks reflect registry updates.
                refreshed_env = _build_status_cmd_env()
                if refreshed_env is not None:
                    os.environ["Path"] = refreshed_env.get("Path", os.environ.get("Path", ""))
                    os.environ["PATH"] = refreshed_env.get("PATH", os.environ.get("PATH", ""))
            except Exception:
                path_updated = False

        status_after = _detect_chiron_global_status()
        return jsonify(
            {
                "status": "ok",
                "path_updated": bool(path_updated),
                "shim_path_updated": bool(shim_path_updated),
                "scripts_path_updated": bool(scripts_path_updated),
                "user_scripts_dir": user_scripts_dir,
                "shim_dir": shim_dir,
                "shim_codex_path": shim_codex,
                "shim_written": bool(shim_written),
                "global_status": status_after,
                "note": "Open a new CMD window if PATH was updated, then click Re-check.",
            }
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Install timed out"}), 504
    except Exception as e:
        _ERROR_LOG.error("webui_routes.install_chiron_global", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-configured/current-values", methods=["GET"])
def get_proxy_configured_current_values() -> Any:
    """Read current values from existing configured script files."""
    try:
        claude_script = Path(_ROOT) / "start_claude_proxy_configured.ps1"
        if not claude_script.is_file():
            return jsonify({"error": "File not found"}), 404

        content = claude_script.read_text(encoding="utf-8")

        # Parse values from Claude script
        base_url = ""
        build_id = ""
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('$ConfiguredBaseUrl'):
                base_url = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('$ConfiguredModel'):
                build_id = line.split('=', 1)[1].strip().strip('"')

        return jsonify({
            "baseUrl": base_url,
            "buildId": build_id,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_configured_current_values", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/proxy-configured/generate", methods=["POST"])
def generate_proxy_configured_scripts() -> Any:
    """Generate or update proxy configured script files."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        base_url = (body.get("baseUrl") or "").strip()
        build_id = (body.get("buildId") or "").strip()

        if not base_url:
            return jsonify({"error": "baseUrl is required"}), 400
        if not build_id:
            return jsonify({"error": "buildId is required"}), 400

        claude_ps1_path = Path(_ROOT) / "start_claude_proxy_configured.ps1"
        codex_ps1_path = Path(_ROOT) / "start_codex_proxy_configured.ps1"
        claude_bat_path = Path(_ROOT) / "start_claude_proxy_configured.bat"
        codex_bat_path = Path(_ROOT) / "start_codex_proxy_configured.bat"

        # Delete existing files if they exist
        for path in [claude_ps1_path, codex_ps1_path, claude_bat_path, codex_bat_path]:
            if path.is_file():
                path.unlink()

        # Generate Claude proxy configured script
        claude_ps1_content = f'''param(
    [string]$ProjectDir = (Get-Location).Path,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

# Configure once, then launch without parameters:
#   .\\start_claude_proxy_configured.ps1
$ConfiguredBaseUrl = "{base_url}"
$ConfiguredModel = "{build_id}"
$ConfiguredAuthToken = "ChironAI"
$ConfiguredExtraArgs = @()

if (-not [string]::IsNullOrWhiteSpace($ConfiguredBaseUrl)) {{
    $env:CHIRON_PROXY_BASE_URL = $ConfiguredBaseUrl
}}
$env:ANTHROPIC_BASE_URL = $env:CHIRON_PROXY_BASE_URL
if (-not [string]::IsNullOrWhiteSpace($ConfiguredAuthToken)) {{
    $env:ANTHROPIC_AUTH_TOKEN = $ConfiguredAuthToken
}}
$env:ANTHROPIC_API_KEY = ""

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {{
    Write-Error "claude CLI was not found in PATH. Install Claude Code CLI first."
    exit 1
}}

Write-Host "Starting Claude Code via ChironAI proxy..."
Write-Host "Base URL: $($env:ANTHROPIC_BASE_URL)"
Write-Host "Project dir: $ProjectDir"

try {{
    $ResolvedProjectDir = (Resolve-Path -LiteralPath $ProjectDir -ErrorAction Stop).Path
}} catch {{
    Write-Error "Project directory not found: $ProjectDir"
    exit 1
}}

$launchArgs = @()
if (-not [string]::IsNullOrWhiteSpace($ConfiguredModel)) {{
    $launchArgs += "--model"
    $launchArgs += $ConfiguredModel
}}
if ($ConfiguredExtraArgs) {{
    $launchArgs += $ConfiguredExtraArgs
}}
if ($CliArgs) {{
    $launchArgs += $CliArgs
}}

Push-Location -LiteralPath $ResolvedProjectDir
try {{
    & claude @launchArgs
    exit $LASTEXITCODE
}} finally {{
    Pop-Location
}}
'''

        # Generate Codex proxy configured script
        codex_ps1_content = f'''param(
    [string]$ProjectDir = (Get-Location).Path,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

# Configure once, then launch without parameters:
#   .\\start_codex_proxy_configured.ps1
$ConfiguredBaseUrl = "{base_url}"
$ConfiguredModel = "{build_id}"
$ConfiguredOpenAiApiKey = "ChironAI"
$ConfiguredExtraArgs = @()

if (-not [string]::IsNullOrWhiteSpace($ConfiguredBaseUrl)) {{
    $env:CHIRON_PROXY_BASE_URL = $ConfiguredBaseUrl
}}
$env:OPENAI_BASE_URL = $env:CHIRON_PROXY_BASE_URL
$env:OPENAI_API_BASE = $env:CHIRON_PROXY_BASE_URL
if (-not [string]::IsNullOrWhiteSpace($ConfiguredOpenAiApiKey)) {{
    $env:OPENAI_API_KEY = $ConfiguredOpenAiApiKey
}}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {{
    Write-Error "codex CLI was not found in PATH. Install Codex CLI first."
    exit 1
}}

Write-Host "Starting Codex via ChironAI proxy..."
Write-Host "Base URL: $($env:OPENAI_BASE_URL)"
Write-Host "Project dir: $ProjectDir"

try {{
    $ResolvedProjectDir = (Resolve-Path -LiteralPath $ProjectDir -ErrorAction Stop).Path
}} catch {{
    Write-Error "Project directory not found: $ProjectDir"
    exit 1
}}

$launchArgs = @()
if (-not [string]::IsNullOrWhiteSpace($ResolvedProjectDir)) {{
    $launchArgs += "--cd"
    $launchArgs += $ResolvedProjectDir
}}
if (-not [string]::IsNullOrWhiteSpace($ConfiguredModel)) {{
    $launchArgs += "--model"
    $launchArgs += $ConfiguredModel
}}
if ($ConfiguredExtraArgs) {{
    $launchArgs += $ConfiguredExtraArgs
}}
if ($CliArgs) {{
    $launchArgs += $CliArgs
}}

& codex @launchArgs
exit $LASTEXITCODE
'''

        # Generate .bat wrappers
        claude_bat_content = '''@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start_claude_proxy_configured.ps1" -ProjectDir "%CD%" %*
'''

        codex_bat_content = '''@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0start_codex_proxy_configured.ps1" -ProjectDir "%CD%" %*
'''

        # Write all files
        claude_ps1_path.write_text(claude_ps1_content, encoding="utf-8")
        codex_ps1_path.write_text(codex_ps1_content, encoding="utf-8")
        claude_bat_path.write_text(claude_bat_content, encoding="utf-8")
        codex_bat_path.write_text(codex_bat_content, encoding="utf-8")

        return jsonify({
            "status": "generated",
            "files": {
                "claude_ps1": str(claude_ps1_path),
                "codex_ps1": str(codex_ps1_path),
                "claude_bat": str(claude_bat_path),
                "codex_bat": str(codex_bat_path),
            }
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.generate_proxy_configured_scripts", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/tester-settings", methods=["GET"])
def get_tester_settings() -> Any:
    """Get Model Tester settings for a session."""
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/tester-settings", methods=["POST"])
def update_tester_settings() -> Any:
    """Save Model Tester settings for a session."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        session_id = body.get("session_id")
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        settings_repo = get_settings_repository()
        settings_repo.save_tester_settings(session_id, body)
        
        return jsonify({"status": "ok"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_tester_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        model = body.get("model")
        prompt_name = body.get("prompt_name")
        temperature = body.get("temperature")
        top_p = body.get("top_p")
        reasoning_level = body.get("reasoning_level")
        top_k = body.get("top_k")
        
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        # Get tester settings if not provided
        settings_repo = get_settings_repository()
        tester_settings = settings_repo.get_tester_settings(session_id) if session_id else None
        if tester_settings:
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
                return jsonify({"error": "model is required"}), 400
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/testing/external-docs/preview", methods=["POST"])
def testing_external_docs_preview() -> Any:
    """
    Testing-only endpoint: discover a GitHub repo by library name, fetch a bounded set of markdown docs,
    and return raw + MD-pipeline-processed markdown for inspection (no indexing, no Qdrant writes).
    """
    if run_pipeline is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    if not _EXTERNAL_DOCS_RAG_AVAILABLE:
        return jsonify({"error": "external_docs_rag module not available"}), 500
    try:
        body = request.get_json(force=True, silent=True) or {}
        library = (body.get("library") or body.get("name") or "").strip()
        if not library:
            return jsonify({"error": "library is required"}), 400

        # Guardrails: clamp payload sizes.
        max_files_raw = body.get("max_files")
        max_chars_raw = body.get("max_chars_per_file")
        pipeline_name = body.get("pipeline_name") or body.get("pipeline")

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
        return jsonify({"error": str(e)}), 500


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
            model_name = get_ollama_chat_model()
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-keyword-collections", methods=["POST"])
def update_rag_keyword_collections() -> Any:
    """Create or update a collection, or replace all. Body: single {id?, name, enabled, keywords} or {collections: [...]}."""
    if get_keyword_collections_repository is None:
        return jsonify({"error": "Keyword collections not available"}), 503
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-keyword-collections/<collection_id>", methods=["DELETE"])
def delete_rag_keyword_collection(collection_id: str) -> Any:
    """Delete a RAG keyword collection."""
    if get_keyword_collections_repository is None:
        return jsonify({"error": "Keyword collections not available"}), 503
    try:
        repo = get_keyword_collections_repository()
        repo.delete_collection(collection_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_rag_keyword_collection", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-trigger-settings", methods=["POST"])
def update_rag_trigger_settings() -> Any:
    """Update RAG trigger threshold (persisted to app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("rag_trigger_threshold")
        if raw is None:
            return jsonify({"error": "rag_trigger_threshold required"}), 400
        val = int(raw)
        if val < 0 or val > 20:
            return jsonify({"error": "rag_trigger_threshold must be between 0 and 20"}), 400
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting("rag_trigger_threshold", str(val))
        return jsonify({"status": "ok", "rag_trigger_threshold": val})
    except ValueError:
        return jsonify({"error": "rag_trigger_threshold must be an integer"}), 400
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_trigger_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-framework-settings", methods=["POST"])
def update_rag_framework_settings() -> Any:
    """
    Update framework docs RAG settings (e.g. latest TTL days).
    """
    try:
        body = request.get_json(force=True, silent=True) or {}
        raw_ttl = body.get("framework_latest_ttl_days")
        if raw_ttl is None:
            return jsonify({"error": "framework_latest_ttl_days required"}), 400
        ttl_days = int(raw_ttl)
        if ttl_days <= 0 or ttl_days > 3650:
            return jsonify({"error": "framework_latest_ttl_days must be between 1 and 3650"}), 400
        settings_repo = get_settings_repository()
        settings_repo.set_app_setting("framework_latest_ttl_days", str(ttl_days))
        return jsonify({"status": "ok", "framework_latest_ttl_days": ttl_days})
    except ValueError:
        return jsonify({"error": "framework_latest_ttl_days must be an integer"}), 400
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_framework_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


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

        default_embed_model = get_ollama_embed_model()
        default_rerank_model = get_ollama_rerank_model()

        raw_embed_model = settings_repo.get_app_setting("rag_embed_model")
        rag_embed_model = (raw_embed_model or "").strip()

        proxy_settings = load_proxy_settings(settings_repo)

        rerank_for_rag = bool(proxy_settings.get("rerank_for_rag", False))
        raw_rerank_model = (proxy_settings.get("rerank_model") or "").strip()
        # For UI convenience, if rerank is enabled but model missing, show default.
        rerank_model = raw_rerank_model if raw_rerank_model else (default_rerank_model if rerank_for_rag else "")

        yaml_hybrid = get_retrieval_bool("hybrid_sparse_enabled", True)
        hybrid_sparse_enabled, hybrid_source = resolve_hybrid_sparse_enabled(
            proxy_settings=proxy_settings,
            yaml_default=yaml_hybrid,
        )

        retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}

        return jsonify(
            {
                "rag_embed_model": rag_embed_model,
                "rerank_for_rag": rerank_for_rag,
                "rerank_model": rerank_model,
                "hybrid_sparse_enabled": hybrid_sparse_enabled,
                "retrieval_advanced": retrieval_advanced,
                "retrieval_yaml_defaults": retrieval_yaml_defaults,
                "defaults": {
                    "rag_embed_model": default_embed_model,
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-model-settings", methods=["POST"])
def update_rag_model_settings() -> Any:
    """Persist embedding + rerank model settings for RAG/Qdrant UI."""
    try:
        from application.rag.retrieval_ui_overrides import RETRIEVAL_UI_BOOL_KEYS, retrieval_bool_with_ui_override

        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()

        default_rerank_model = get_ollama_rerank_model()

        rag_embed_model = str(body.get("rag_embed_model") or "").strip()
        settings_repo.set_app_setting("rag_embed_model", rag_embed_model)

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

        default_embed_model = get_ollama_embed_model()
        retrieval_advanced = {k: retrieval_bool_with_ui_override(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        retrieval_yaml_defaults = {k: _retrieval_yaml_raw_bool(k) for k in sorted(RETRIEVAL_UI_BOOL_KEYS)}
        return jsonify(
            {
                "status": "ok",
                "rag_embed_model": rag_embed_model,
                "rerank_for_rag": rerank_for_rag,
                "rerank_model": proxy_settings.get("rerank_model") or "",
                "hybrid_sparse_enabled": hybrid_sparse_enabled,
                "retrieval_advanced": retrieval_advanced,
                "retrieval_yaml_defaults": retrieval_yaml_defaults,
                "defaults": {
                    "rag_embed_model": default_embed_model,
                    "rerank_model": default_rerank_model,
                    "hybrid_sparse_enabled": yaml_hybrid,
                },
            }
        )
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_rag_model_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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


def open_webui_status() -> Any:
    """Return Open WebUI status from Docker: running if container matching OPEN_WEBUI_CONTAINER_NAME is up."""
    try:
        def _compute() -> dict[str, Any]:
            return open_webui_status_snapshot(ping_timeout_sec=0.6)

        status = _get_cached_status("open_webui_status", ttl_sec=2.0, compute=_compute)
        return jsonify(status)
    except Exception as e:
        _WEBUI_LOG.warning("open_webui_status: %s", e)
        u = os.getenv("OPEN_WEBUI_URL", "http://localhost:3000").rstrip("/")
        return jsonify({"url": u, "running": False, "error": str(e)})


def open_webui_start() -> Any:
    """Try to start Open WebUI Docker container."""
    try:
        cfg = get_open_webui_config()
        override_ollama_url: str | None = None
        name = cfg.open_webui_container_name
        try:
            settings_repo = get_settings_repository()
            saved = (settings_repo.get_app_setting(OPEN_WEBUI_OLLAMA_BASE_URL_APP_KEY) or "").strip()
            if saved:
                override_ollama_url = _normalize_open_webui_ollama_base_url(saved)
        except ValueError as e:
            return (
                jsonify({"ok": False, "output": f"Invalid saved Open WebUI backend URL: {e}", "container": name}),
                400,
            )
        ok, output, _name = start_open_webui_service(
            open_webui_ollama_url_for_container=override_ollama_url,
        )
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output, "container": name}), status
    except Exception as e:
        _WEBUI_LOG.error("open_webui_start: %s", e, exc_info=True)
        return jsonify(
            {"ok": False, "output": str(e), "container": os.getenv("OPEN_WEBUI_CONTAINER_NAME", "open-webui")}
        ), 500


def open_webui_stop() -> Any:
    """Try to stop Open WebUI Docker container."""
    try:
        ok, output, name = stop_open_webui_service()
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output, "container": name}), status
    except Exception as e:
        _WEBUI_LOG.error("open_webui_stop: %s", e, exc_info=True)
        return jsonify(
            {"ok": False, "output": str(e), "container": os.getenv("OPEN_WEBUI_CONTAINER_NAME", "open-webui")}
        ), 500


def _open_webui_config_put() -> Any:
    """Persist Open WebUI Ollama-compatible backend base URL (empty = use env/default)."""
    body = request.get_json(silent=True) or {}
    if "open_webui_ollama_base_url" not in body:
        return jsonify({"ok": False, "error": "missing open_webui_ollama_base_url"}), 400
    raw = body.get("open_webui_ollama_base_url")
    settings_repo = get_settings_repository()
    s = (str(raw) if raw is not None else "").strip()
    if not s:
        settings_repo.set_app_setting(OPEN_WEBUI_OLLAMA_BASE_URL_APP_KEY, "")
        return jsonify({"ok": True, "open_webui_ollama_base_url": ""})
    try:
        norm = _normalize_open_webui_ollama_base_url(s)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    settings_repo.set_app_setting(OPEN_WEBUI_OLLAMA_BASE_URL_APP_KEY, norm)
    return jsonify({"ok": True, "open_webui_ollama_base_url": norm})


def open_webui_config() -> Any:
    """Return effective Open WebUI Docker settings; PUT saves backend URL to app_settings."""
    if request.method == "PUT":
        try:
            return _open_webui_config_put()
        except Exception as e:
            _WEBUI_LOG.error("open_webui_config PUT: %s", e, exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500
    try:
        cfg = get_open_webui_config()
        settings_repo = get_settings_repository()
        saved_raw = (settings_repo.get_app_setting(OPEN_WEBUI_OLLAMA_BASE_URL_APP_KEY) or "").strip()
        saved_norm = ""
        if saved_raw:
            try:
                saved_norm = _normalize_open_webui_ollama_base_url(saved_raw)
            except ValueError:
                saved_norm = saved_raw.rstrip("/")
        env_set = bool((os.getenv("OPEN_WEBUI_OLLAMA_BASE_URL") or "").strip())
        cfg_ollama = (cfg.open_webui_ollama_url_for_container or "").strip().rstrip("/")
        effective = saved_norm if saved_norm else cfg_ollama
        if saved_norm:
            source = "saved"
        elif env_set:
            source = "environment"
        else:
            source = "default"
        port = get_server_port()
        llm_proxy_hint = f"http://host.docker.internal:{port}"
        return jsonify(
            {
                "open_webui_host_url": cfg.open_webui_host_url,
                "open_webui_container_name": cfg.open_webui_container_name,
                "open_webui_image": cfg.open_webui_image,
                "open_webui_host_port": cfg.open_webui_host_port,
                "open_webui_container_port": cfg.open_webui_container_port,
                "open_webui_ollama_url_for_container": effective,
                "open_webui_ollama_base_url_saved": saved_norm or "",
                "open_webui_ollama_base_url_effective": effective,
                "open_webui_ollama_base_url_source": source,
                "llm_proxy_ollama_base_hint": llm_proxy_hint,
            }
        )
    except Exception as e:
        _WEBUI_LOG.warning("open_webui_config: %s", e)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/ollama/status", methods=["GET"])
def ollama_status() -> Any:
    """Check if Ollama is reachable at the same base URL as RAG/chat (default http://localhost:11434).

    Not ServiceStarter's OLLAMA_PORT (11343): the header reflects where models and proxy actually talk.
    """
    url = _get_ollama_url().rstrip("/")
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        ping_o = invoke_ping(base_url=url, timeout=3.0)
        status["http_status"] = int(ping_o.get("status_code") or 0)
        if ping_o.get("ok"):
            status["running"] = True
        err = ping_o.get("error")
        if err:
            status["error"] = str(err)
    except Exception as e:
        status["error"] = str(e)
    return jsonify(status)


@webui_bp.route("/ollama/start", methods=["POST"])
def ollama_start() -> Any:
    """Try to start Ollama server (best-effort install on Windows, then ollama serve)."""
    try:
        ok, output = start_ollama_service()
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output}), status
    except Exception as e:
        # If ServiceStarter import/setup failed but Ollama is already alive, report success.
        try:
            ping_o = invoke_ping(base_url=_get_ollama_url().rstrip("/"), timeout=3.0)
            if ping_o.get("ok"):
                return jsonify({"ok": True, "output": "Ollama already running"}), 200
        except Exception:
            pass
        _WEBUI_LOG.error("ollama_start: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e)}), 500


@webui_bp.route("/ollama/stop", methods=["POST"])
def ollama_stop() -> Any:
    """Stop Ollama using the same port as WebUI/RAG (e.g. 11434), not only ServiceStarter defaults."""
    try:
        ok, output = stop_ollama_service(base_url=_get_ollama_url(), default_port=11434)
        status = 200 if ok else 500
        return jsonify({"ok": ok, "output": output}), status
    except Exception as e:
        _WEBUI_LOG.error("ollama_stop: %s", e, exc_info=True)
        return jsonify({"ok": False, "output": str(e)}), 500


@webui_bp.route("/ollama/library", methods=["GET"])
def ollama_library() -> Any:
    """Full Ollama tag list for the Ollama tab (includes hidden flags; not filtered like GET /models)."""
    url = _get_ollama_url().rstrip("/")
    hidden_set = get_hidden_ollama_model_ids()
    hidden_ids = sorted(hidden_set)
    try:
        data = invoke_tags(base_url=url, timeout=30.0)
        models: list[dict[str, Any]] = []
        for m in data.get("models") or []:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or m.get("model") or "").strip()
            if not name:
                continue
            models.append(
                {
                    "name": name,
                    "size": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                    "digest": m.get("digest"),
                    "hidden": name in hidden_set,
                }
            )
        return jsonify({"ok": True, "url": url, "models": models, "hidden_ids": hidden_ids})
    except Exception as e:
        _WEBUI_LOG.warning("ollama_library: %s", e)
        return jsonify(
            {
                "ok": False,
                "url": url,
                "models": [],
                "hidden_ids": hidden_ids,
                "error": str(e),
            }
        )


@webui_bp.route("/ollama/hidden", methods=["PATCH"])
def ollama_hidden_patch() -> Any:
    """Add/remove model names from the editor deny-list."""
    body = request.get_json(silent=True) or {}
    raw_add = body.get("add")
    raw_remove = body.get("remove")
    add = raw_add if isinstance(raw_add, list) else []
    remove = raw_remove if isinstance(raw_remove, list) else []
    try:
        updated = patch_hidden_ollama_model_ids(add=add, remove=remove)
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
    url = _get_ollama_url().rstrip("/")
    try:
        details = invoke_show(base_url=url, name=model, timeout=120.0)
        return jsonify({"ok": True, "details": details})
    except OllamaInteractorCliError as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@webui_bp.route("/ollama/delete", methods=["POST"])
def ollama_delete_model() -> Any:
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model is required"}), 400
    url = _get_ollama_url().rstrip("/")
    try:
        result = invoke_delete(base_url=url, name=model, timeout=120.0)
        return jsonify({"ok": True, "result": result})
    except OllamaInteractorCliError as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@webui_bp.route("/ollama/pull", methods=["POST"])
def ollama_pull_stream() -> Any:
    """Stream Ollama pull progress as NDJSON."""
    body = request.get_json(silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    insecure = bool(body.get("insecure"))
    url = _get_ollama_url().rstrip("/")
    read_timeout = float(body.get("timeout", 86400.0) or 86400.0)
    read_timeout = max(60.0, min(read_timeout, 86400.0 * 2))

    def generate():
        try:
            for obj in iter_pull_objects(
                base_url=url,
                name=model,
                insecure=insecure,
                read_timeout=read_timeout,
            ):
                yield json.dumps(obj, ensure_ascii=False) + "\n"
        except OllamaInteractorCliError as e:
            yield json.dumps({"error": str(e)}) + "\n"
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
        return jsonify({"error": str(e)}), 500


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
    embed_model_override: str | None = None,
) -> list[list[float]]:
    """Simple embedding function using Ollama.

    When ``embed_model_override`` is non-empty, it is used for this call only
    (e.g. create-collection job). Otherwise: app_settings, then env, then default.
    """
    if not texts:
        return []

    embed_url = get_ollama_embed_url()
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
        # 2) get_ollama_embed_model() (env RAG_EMBED_MODEL + config/models.yaml)
        embed_model = rag_embed_model or get_ollama_embed_model()
    
    try:
        data = invoke_embed(
            {
                "url": embed_url,
                "json": {"model": embed_model, "input": texts},
                "timeout": 300,
            },
            default_timeout=300,
        )
        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError(f"Expected {len(texts)} embeddings, got {len(embeddings)}")
        return embeddings
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
                embed_texts, embed_model_override=embed_model
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
        return jsonify({"error": str(e)}), 500


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
                return jsonify({"error": "Source not found"}), 404
            
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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/sources/<source_id>/pages", methods=["GET"])
def get_crawler_source_pages(source_id: str) -> Any:
    """Get detailed page list for a source."""
    try:
        meta = _load_source_meta(source_id)
        if not meta:
            return jsonify({"error": "Source not found"}), 404
        
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/indexer-tester/sources/<source_id>/files", methods=["GET"])
def get_indexer_tester_files(source_id: str) -> Any:
    """
    List markdown files for a specific source, with optional sorting by name or size.
    """
    try:
        sources_dir = _get_crawler_sources_dir()
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        if not os.path.isdir(pages_dir):
            return jsonify({"error": "Source pages directory not found"}), 404

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
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/indexer-tester/sources/<source_id>/files/<path:filename>", methods=["GET"])
def get_indexer_tester_file_detail(source_id: str, filename: str) -> Any:
    """
    Return original and processed markdown for a specific page using WebUI/app.py pipeline.
    """
    try:
        sources_dir = _get_crawler_sources_dir()
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        if not os.path.isdir(pages_dir):
            return jsonify({"error": "Source pages directory not found"}), 404

        # Normalize and validate path to stay under pages_dir
        requested_path = os.path.abspath(os.path.join(pages_dir, filename))
        pages_dir_abs = os.path.abspath(pages_dir)
        if not requested_path.startswith(pages_dir_abs + os.sep):
            return jsonify({"error": "Invalid filename"}), 400
        basename = os.path.basename(requested_path)
        if not basename.lower().endswith(".md"):
            return jsonify({"error": "Only .md files are supported"}), 400
        if not os.path.isfile(requested_path):
            return jsonify({"error": "File not found"}), 404

        meta = _load_source_meta(source_id) or {}
        page_entry = (meta.get("pages") or {}).get(basename, {})

        with open(requested_path, "r", encoding="utf-8") as f:
            source_md = f.read()

        pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
        if run_pipeline is None:
            return jsonify({"error": "md_indexer module not available"}), 500
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
        return jsonify({"error": str(e)}), 500


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
    return chat_client.chat(ollama_messages, use_model, stream=False, options=options) or ""


def _batch_eval_worker(job_id: str, source_id: str, model: str | None, count: int) -> None:
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
            return jsonify({"error": "At least one of source_md or processed_md is required"}), 400

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
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        _ERROR_LOG.error("webui_routes.indexer_tester_evaluate", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/indexer-tester/evaluate-batch", methods=["POST"])
def start_indexer_tester_evaluate_batch() -> Any:
    """Start a batch LLM evaluation job. Body: { source_id, model?, count }. Returns job_id."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        source_id = (body.get("source_id") or "").strip()
        count = body.get("count")
        model = (body.get("model") or "").strip() or None
        if not source_id:
            return jsonify({"error": "source_id is required"}), 400
        try:
            count = int(count) if count is not None else 0
        except (TypeError, ValueError):
            count = 0
        if count < 1 or count > 500:
            return jsonify({"error": "count must be between 1 and 500"}), 400

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
            args=(job_id, source_id, model, count),
            daemon=True,
        )
        thread.start()
        return jsonify({"job_id": job_id})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.start_indexer_tester_evaluate_batch", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/indexer-tester/evaluate-batch/status/<job_id>", methods=["GET"])
def get_indexer_tester_evaluate_batch_status(job_id: str) -> Any:
    """Return batch job state: status, total, done, current_file, results, error."""
    with _batch_eval_lock:
        job = _batch_eval_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
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
        model = (body.get("model") or "").strip() or None
        if not results or not isinstance(results, list):
            return jsonify({"error": "results array is required"}), 400

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
            return jsonify({"error": "No valid results to analyze"}), 400
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
            return jsonify({"error": "No chat model configured"}), 400

        system_prompt = BATCH_PATTERNS_SYSTEM_PROMPT
        ollama_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options = {"temperature": 0.0}
        patterns = chat_client.chat(ollama_messages, use_model, stream=False, options=options) or ""
        return jsonify({"patterns": (patterns or "").strip()})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.detect_batch_eval_patterns", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ---- MD Pipelines (config-driven markdown cleanup) ----

@webui_bp.route("/crawler/md-pipelines", methods=["GET"])
def get_md_pipelines_list() -> Any:
    """List available pipeline names (config/md_pipelines/*.json)."""
    if list_pipeline_names is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    try:
        names = list_pipeline_names()
        return jsonify({"pipelines": names})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_md_pipelines_list", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["GET"])
def get_md_pipeline(name: str) -> Any:
    """Get pipeline JSON by name."""
    if load_pipeline is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    try:
        pipeline = load_pipeline(name)
        if pipeline is None:
            return jsonify({"error": f"Pipeline '{name}' not found"}), 404
        return jsonify(pipeline.to_dict())
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_md_pipeline", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["PUT", "POST"])
def save_md_pipeline(name: str) -> Any:
    """Save pipeline JSON by name. Body: { "name": "...", "steps": [...] }."""
    if save_pipeline is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    try:
        body = request.get_json(force=True, silent=True) or {}
        if "steps" not in body:
            return jsonify({"error": "Missing 'steps' in body"}), 400
        from modules.md_indexer.domain.schema import Pipeline
        pipeline = Pipeline.from_dict(body)
        save_pipeline(name, pipeline)
        return jsonify({"ok": True, "name": name})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.save_md_pipeline", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/md-pipelines/<name>", methods=["DELETE"])
def delete_md_pipeline(name: str) -> Any:
    """Delete pipeline by name."""
    if md_indexer_delete_pipeline is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    try:
        if md_indexer_delete_pipeline(name):
            return jsonify({"ok": True, "name": name})
        return jsonify({"error": f"Pipeline '{name}' not found"}), 404
    except Exception as e:
        _ERROR_LOG.error("webui_routes.delete_md_pipeline", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/md-pipelines/preview", methods=["POST"])
def preview_md_pipeline() -> Any:
    """Run a pipeline on a source file and return source_md + processed_md."""
    if run_pipeline is None:
        return jsonify({"error": "md_indexer module not available"}), 500
    try:
        body = request.get_json(force=True, silent=True) or {}
        pipeline_name = body.get("pipeline_name") or body.get("pipeline")
        source_id = body.get("source_id")
        filename = body.get("filename")
        if not source_id or not filename:
            return jsonify({"error": "Missing source_id or filename"}), 400
        sources_dir = _get_crawler_sources_dir()
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        if not os.path.isdir(pages_dir):
            return jsonify({"error": "Source pages directory not found"}), 404
        requested_path = os.path.abspath(os.path.join(pages_dir, filename))
        pages_dir_abs = os.path.abspath(pages_dir)
        if not requested_path.startswith(pages_dir_abs + os.sep):
            return jsonify({"error": "Invalid filename"}), 400
        basename = os.path.basename(requested_path)
        if not basename.lower().endswith(".md"):
            return jsonify({"error": "Only .md files are supported"}), 400
        if not os.path.isfile(requested_path):
            return jsonify({"error": "File not found"}), 404
        with open(requested_path, "r", encoding="utf-8") as f:
            source_md = f.read()
        if pipeline_name is None and get_active_pipeline_name is not None:
            pipeline_name = get_active_pipeline_name()
        page_meta, processed_md = run_pipeline(pipeline_name, source_md)
        return jsonify({
            "source_id": source_id,
            "filename": basename,
            "page_meta": page_meta,
            "source_md": source_md,
            "processed_md": processed_md,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.preview_md_pipeline", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/sources/<source_id>/stats", methods=["GET"])
def get_crawler_source_stats(source_id: str) -> Any:
    """Get statistics for a source."""
    try:
        meta = _load_source_meta(source_id)
        if not meta:
            return jsonify({"error": "Source not found"}), 404
        
        stats = _get_source_stats(meta)
        return jsonify({
            "source_id": source_id,
            **stats,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_crawler_source_stats", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
                return jsonify({"error": "WebUI/app.py not found"}), 500
            
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
            return jsonify({"error": "WebUI/app.py not found"}), 500
        
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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


@webui_bp.route("/crawler/sources", methods=["POST"])
def add_crawler_source() -> Any:
    """Add a new crawl source."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        source_id = body.get("id", "").strip()
        url = body.get("url", "").strip()
        max_depth = int(body.get("max_depth", 2))
        crawler = body.get("crawler", "playwright")
        doc_only = bool(body.get("doc_only", True))
        seed_urls_raw = body.get("seed_urls", [])
        # Filter out empty strings and normalize
        seed_urls = [s.strip() for s in seed_urls_raw if s and s.strip()]
        
        if not source_id:
            return jsonify({"error": "Source ID is required"}), 400
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        # Validate source_id format (alphanumeric, underscore, hyphen)
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", source_id):
            return jsonify({"error": "Source ID must contain only alphanumeric characters, underscores, and hyphens"}), 400
        
        # Load existing sources
        sources = _load_sources_config()
        
        # Check if source already exists
        if any(s.get("id") == source_id for s in sources):
            return jsonify({"error": f"Source '{source_id}' already exists"}), 409
        
        # Add new source
        new_source = {
            "id": source_id,
            "url": url,
            "max_depth": max_depth,
            "crawler": crawler,
            "doc_only": doc_only,
            "seed_urls": seed_urls,
        }
        sources.append(new_source)
        
        # Save to YAML
        if not _save_sources_config(sources):
            return jsonify({"error": "Failed to save source configuration"}), 500
        
        # Create source directory and initial meta.json
        sources_dir = _get_crawler_sources_dir()
        source_dir = os.path.join(sources_dir, source_id)
        os.makedirs(source_dir, exist_ok=True)
        
        meta = {
            "source_id": source_id,
            "source_url": url,
            "max_depth": max_depth,
            "crawler": crawler,
            "doc_only": doc_only,
            "seed_urls": seed_urls,
            "last_crawled": None,
            "hash_algo": "sha256",
            "pages": {},
        }
        
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            "status": "created",
            "source_id": source_id,
            "message": f"Source '{source_id}' created successfully.",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.add_crawler_source", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/crawler/sources/<source_id>", methods=["PUT"])
def update_crawler_source(source_id: str) -> Any:
    """Update an existing crawl source."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        url = body.get("url", "").strip()
        max_depth = int(body.get("max_depth", 2))
        crawler = body.get("crawler", "playwright")
        doc_only = bool(body.get("doc_only", True))
        seed_urls_raw = body.get("seed_urls", [])
        # Filter out empty strings and normalize
        seed_urls = [s.strip() for s in seed_urls_raw if s and s.strip()]
        
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        # Load existing sources
        sources = _load_sources_config()
        
        # Find and update source
        source_found = False
        for i, source in enumerate(sources):
            if source.get("id") == source_id:
                sources[i] = {
                    "id": source_id,
                    "url": url,
                    "max_depth": max_depth,
                    "crawler": crawler,
                    "doc_only": doc_only,
                    "seed_urls": seed_urls,
                }
                source_found = True
                break
        
        if not source_found:
            return jsonify({"error": f"Source '{source_id}' not found"}), 404
        
        # Save to YAML
        if not _save_sources_config(sources):
            return jsonify({"error": "Failed to save source configuration"}), 500
        
        # Update meta.json if it exists
        meta = _load_source_meta(source_id)
        if meta:
            meta["source_url"] = url
            meta["max_depth"] = max_depth
            meta["crawler"] = crawler
            meta["doc_only"] = doc_only
            meta["seed_urls"] = seed_urls
            
            sources_dir = _get_crawler_sources_dir()
            meta_path = os.path.join(sources_dir, source_id, "meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            "status": "updated",
            "source_id": source_id,
            "message": f"Source '{source_id}' updated successfully.",
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_crawler_source", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _run_create_collection_job(
    job_id: str,
    collection_name: str,
    source_ids: list[str],
    chunk_max_size: int,
    chunk_min_size: int,
    embed_model: str | None = None,
) -> None:
    """Background task: run indexing and update job progress."""
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
        return jsonify({"error": "Job not found", "job_id": job_id}), 404
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
            return jsonify({"error": "Job not found", "job_id": job_id}), 404
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
        embed_model_raw = str(body.get("rag_embed_model") or "").strip()
        embed_model = embed_model_raw or None

        if not collection_name:
            return jsonify({"error": "collection_name is required"}), 400

        if not source_ids:
            return jsonify({"error": "At least one source_id is required"}), 400

        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", collection_name):
            return jsonify({"error": "Collection name must contain only alphanumeric characters, underscores, and hyphens"}), 400

        qdrant_url = get_qdrant_url().rstrip("/")
        qclient = QdrantClient(url=qdrant_url)
        try:
            qclient.get_collection(collection_name)
            return jsonify({"error": f"Collection '{collection_name}' already exists"}), 409
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
                collection_name,
                available_sources,
                chunk_max_size,
                chunk_min_size,
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
        return jsonify({"error": str(e)}), 500

__all__ = ["webui_bp"]
