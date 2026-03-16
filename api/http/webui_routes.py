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
from subprocess import run, Popen
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import threading
import uuid

from flask import Blueprint, Response, current_app, jsonify, request

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# So that "from rag_service ..." works (rag_service package lives in modules/rag_service).
_MODULES_RAG = os.path.join(_ROOT, "modules", "rag_service")
if _MODULES_RAG not in sys.path:
    sys.path.insert(0, _MODULES_RAG)
# External docs RAG (on-demand fetch, GitHub discovery).
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)

from application.container import default_rerank_client
from application.rag.collection_freshness import check_collection_freshness
from application.rag.params import RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages

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
    get_ollama_chat_model,
    get_ollama_rerank_model,
    get_qdrant_url,
    get_rag_float,
    get_rag_int,
    get_rag_prompt_name,
    get_retrieval_int,
)
from domain.services.rag_trigger import compute_rag_trigger_score
from config.rag_prompts import (
    get_rag_system_prompt_swift_mode,
    list_rag_prompt_names,
    PROMPTS_DIR,
    load_prompt,
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


from domain.entities.rag import RagQuestionRequest
from domain.services.prompt_builder import (
    determine_reasoning_level,
    last_user_content,
    build_system_content,
)
from infrastructure.database import (
    get_session_manager,
    get_logs_repository,
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

import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct, PointIdsList, PayloadSchemaType
from qdrant_client.http.exceptions import ResponseHandlingException

# Import domain services for indexing
from domain.services.chunking import (
    CHUNK_MAX_SIZE,
    CHUNK_MIN_SIZE,
    chunk_quality_ok,
    split_markdown_into_chunks,
)
from domain.services.markdown_meta import parse_and_strip_meta_block
from domain.services.metadata_inference import (
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)

# Import config for embeddings
try:
    from config import get_ollama_embed_url, get_indexing_int
except ImportError:
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore
    get_indexing_int = lambda k, d: d  # type: ignore

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
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import importlib.util

# In-memory buffer for dev console (last 50 requests)
_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

webui_bp = Blueprint("webui", __name__, url_prefix="/api/webui")


_INDEXER_APP_MODULE = None


def _get_indexer_app_module():
    """
    Lazy-load WebUI/app.py as a module so we can reuse its markdown index pipeline
    (process_markdown_for_index) without duplicating logic.
    """
    global _INDEXER_APP_MODULE
    if _INDEXER_APP_MODULE is not None:
        return _INDEXER_APP_MODULE

    app_path = _get_webui_app_path()
    if not os.path.isfile(app_path):
        raise RuntimeError("WebUI/app.py not found")

    spec = importlib.util.spec_from_file_location("tmrag_webui_app_indexer", app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load WebUI/app.py module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    _INDEXER_APP_MODULE = module
    return module


@webui_bp.route("/models", methods=["GET"])
def get_models() -> Any:
    """Return list of available models from Ollama."""
    try:
        ollama_url = _get_ollama_url()
        tags_url = f"{ollama_url}/api/tags"
        
        models_list = []
        
        # Try to get models from Ollama
        try:
            resp = requests.get(tags_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                ollama_models = data.get("models", [])
                for model in ollama_models:
                    model_name = model.get("name", "")
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
        
        # Always add RAG proxy model as first option
        models_list.insert(0, {
            "id": "rag-ollama",
            "name": "rag-ollama",
            "description": "RAG-enabled Ollama model (proxy)",
        })
        
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
            "swift_modes": ["default", "swift5", "swift6"],
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


@webui_bp.route("/proxy-logs", methods=["GET"])
def get_proxy_logs() -> Any:
    """Return proxy logs from database."""
    try:
        limit = int(request.args.get("limit", 100))
        since_id = request.args.get("since_id")
        from_date = request.args.get("from")
        to_date = request.args.get("to")

        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id="proxy",
            level="INFO",
            limit=limit,
            since_id=int(since_id) if since_id else None,
            source="proxy",
            from_date=from_date or None,
            to_date=to_date or None,
        )

        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_proxy_logs", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
    - swift_mode: optional ("swift5", "swift6", "default")
    - prompt_name: optional prompt name override
    - include_rag_metadata: optional bool (default True for WebUI)
    
    Returns:
    - Standard OpenAI format response
    - Plus: rag_metadata with chunks_info, latency_ms, system_prompt_preview
    """
    start_time = time.time()
    try:
        body = request.get_json(force=True, silent=True) or {}
        messages = body.get("messages") or []
        requested_model = body.get("model") or "rag-ollama"
        temperature = body.get("temperature")
        top_p = body.get("top_p")
        reasoning_level = body.get("reasoning_level")
        code_only = body.get("code_only", False)
        swift_mode = body.get("swift_mode", "default")
        prompt_name = body.get("prompt_name")
        include_rag_metadata = body.get("include_rag_metadata", True)
        
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        set_proxy_status(STATUS_RAG_SEARCH)
        
        # Get model settings for proxy requests
        if requested_model == "rag-ollama":
            settings_repo = get_settings_repository()
            stored_model = settings_repo.get_app_setting("proxy_model")
            if stored_model:
                requested_model = stored_model
        
        # Get collection name from request or settings; no config default — use first available or error
        collection_name = (body.get("collection_name") or "").strip() or None
        if not collection_name:
            settings_repo = get_settings_repository()
            collection_name = (settings_repo.get_app_setting("rag_collection") or "").strip() or None
        if not collection_name:
            names = _get_qdrant_collection_names()
            if not names:
                return jsonify({
                    "error": "No Qdrant collections. Create one in Crawler / RAG then try again.",
                }), 400
            collection_name = names[0]

        # Get RAG dependencies - try to find WebUI directory
        webui_dir = None
        possible_webui = os.path.join(_ROOT, "WebUI")
        if os.path.isdir(possible_webui):
            webui_dir = possible_webui
        params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
        
        # Get prompt with Swift mode
        prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
        
        # Override params if prompt_name provided
        if prompt_name:
            params = params._replace(system_prefix=prefix, system_suffix=suffix)
        
        rag_repo = deps.rag_repo
        embed_provider = deps.embed_provider
        rerank_client = deps.rerank_client
        chat_client = deps.chat_client
        
        # Rerank on/off and model from model settings (default off)
        use_rerank = False
        rerank_model_override: str | None = None
        try:
            settings_repo = get_settings_repository()
            proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
            if proxy_settings_json:
                proxy_settings = json.loads(proxy_settings_json)
                use_rerank = bool(proxy_settings.get("rerank_for_rag", False))
                rm = (proxy_settings.get("rerank_model") or "").strip() or None
                if rm:
                    rerank_model_override = rm
        except Exception:
            pass
        if use_rerank:
            effective_rerank_client = default_rerank_client(model=rerank_model_override)
        else:
            effective_rerank_client = None
        
        last_user = last_user_content(messages)
        context_length = len(last_user.split())
        # Use requested model if it's not "rag-ollama", otherwise use config model
        ollama_model = requested_model if requested_model != "rag-ollama" else params.model_name
        
        # Determine reasoning level
        if not reasoning_level:
            reasoning_level = determine_reasoning_level(
                last_user, context_length, ollama_model, None
            )
        
        # Build RAG context to get chunks_info
        rag_keywords = _get_rag_required_keywords_from_module()
        trigger_threshold = _get_effective_rag_trigger_threshold()
        ctx, rag_timings = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            effective_rerank_client,
            params.context_chunk_chars,
            params.context_total_chars,
            rag_required_keywords=rag_keywords,
            trigger_threshold=trigger_threshold,
        )
        if rag_timings:
            set_latest_request_rag_steps(rag_timings)
        set_proxy_status(STATUS_PREPARING_RESPONSE)
        
        # Prepare messages
        req = RagQuestionRequest(
            messages=messages,
            model=ollama_model,  # Use ollama_model (already resolved from requested_model)
            stream=False,
            reasoning_level=reasoning_level,
        )
        
        ollama_messages, use_model = prepare_ollama_messages(
            req,
            rag_repo,
            embed_provider,
            effective_rerank_client,
            prefix,
            suffix,
            params.context_chunk_chars,
            params.context_total_chars,
            params.confidence_threshold,
            ollama_model,
            reasoning_level=reasoning_level,
            rag_required_keywords=rag_keywords,
            rag_context=ctx,
            trigger_threshold=trigger_threshold,
        )
        # Ensure use_model is not "rag-ollama" - use config model if needed
        if use_model == "rag-ollama":
            use_model = params.model_name

        # Add code_only instruction if requested
        if code_only:
            user_msg = ollama_messages[-1] if ollama_messages else None
            if user_msg and user_msg.get("role") == "user":
                user_msg["content"] = "Только код, без пояснений. " + (user_msg.get("content") or "")
        
        # Prepare Ollama options
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = float(temperature)
        if top_p is not None:
            options["top_p"] = float(top_p)
        
        # Call chat
        set_proxy_status(STATUS_RESPONSE)
        content = chat_client.chat(ollama_messages, use_model, stream=False, options=options if options else None)
        _pt = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
        latency_ms = int((time.time() - start_time) * 1000)

        def _approx_tokens(text: str) -> int:
            if not text:
                return 0
            return max(1, int(len(text) / 4))

        prompt_tokens = _approx_tokens(_pt)
        completion_tokens = _approx_tokens(content or "")
        total_tokens = prompt_tokens + completion_tokens
        set_latest_request_total_tokens(total_tokens)

        # Build response
        response_data: dict[str, Any] = {
            "id": f"chatcmpl-webui-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": use_model,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content or ""},
                "finish_reason": "stop",
            }],
        }

        # Add RAG metadata if requested
        if include_rag_metadata:
            system_preview = ollama_messages[0].get("content", "")[:500] if ollama_messages else ""
            if len(ollama_messages[0].get("content", "")) > 500:
                system_preview += "..."
            
            response_data["rag_metadata"] = {
                "chunks_info": ctx.chunks_info,
                "max_score": ctx.max_score,
                "chunks_count": len(ctx.chunks_info),
                "latency_ms": latency_ms,
                "context_chars": sum(int(c.get("text_length") or 0) for c in (ctx.chunks_info or [])),
                "system_prompt_preview": system_preview,
            }
        
        # Store in buffer for dev console
        _REQUEST_BUFFER.append({
            "timestamp": datetime.now().isoformat(),
            "request": {
                "messages": messages,
                "model": use_model,
                "temperature": temperature,
                "top_p": top_p,
                "reasoning_level": reasoning_level,
                "swift_mode": swift_mode,
                "code_only": code_only,
            },
            "response": response_data,
            "latency_ms": latency_ms,
        })
        
        return jsonify(response_data)
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
        
        # Get stored proxy model or use default
        stored_model = settings_repo.get_app_setting("proxy_model")
        stored_settings_json = settings_repo.get_app_setting("proxy_settings")
        
        default_settings = {
            "model": stored_model or get_ollama_chat_model(),
            "prompt_name": get_rag_prompt_name(),
            "swift_mode": "default",
            "temperature": get_rag_float("temperature", 0.0),
            "top_p": get_rag_float("top_p", 0.1),
            "reasoning_level": "",
            "code_only": False,
            "include_rag_metadata": True,
            "rerank_for_rag": False,
            "rerank_model": get_ollama_rerank_model(),
        }
        
        # Merge stored settings if available
        if stored_settings_json:
            try:
                stored_settings = json.loads(stored_settings_json)
                default_settings.update(stored_settings)
            except json.JSONDecodeError:
                pass
        
        return jsonify(default_settings)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_model_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/model-settings", methods=["POST"])
def update_model_settings() -> Any:
    """Update model settings (persisted to app_settings)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        settings_repo = get_settings_repository()
        if body.get("model") is not None:
            settings_repo.set_app_setting("proxy_model", str(body["model"]))
        settings_repo.set_app_setting("proxy_settings", json.dumps(body))
        return jsonify({"status": "ok", "settings": body})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.update_model_settings", exc_info=True)
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
            # Return defaults from RAG config
            return jsonify({
                "model": "",
                "prompt_name": get_rag_prompt_name(),
                "swift_mode": "default",
                "temperature": 0.0,
                "top_p": 0.1,
                "reasoning_level": "",
                "use_rag": True,
                "top_k": get_rag_int("top_k", 4),
                "rag_collection": "",
            })
        
        # Ensure rag_collection field exists
        if "rag_collection" not in settings:
            settings["rag_collection"] = ""
        
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
        swift_mode = body.get("swift_mode", "default")
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
            swift_mode = swift_mode or tester_settings.get("swift_mode", "default")
            temperature = temperature if temperature is not None else tester_settings.get("temperature")
            top_p = top_p if top_p is not None else tester_settings.get("top_p")
            reasoning_level = reasoning_level or tester_settings.get("reasoning_level")
            use_rag = use_rag if "use_rag" in body else tester_settings.get("use_rag", True)
            top_k = top_k if top_k is not None else tester_settings.get("top_k")
            if "fetch_web_knowledge" not in body:
                fetch_web_knowledge = tester_settings.get("fetch_web_knowledge", False)
        
        # Get collection name from request, tester settings, or global settings; no config default
        collection_name = (body.get("collection_name") or "").strip() or None
        if not collection_name and tester_settings:
            collection_name = (tester_settings.get("rag_collection") or "").strip() or None
        if not collection_name or collection_name == "":
            collection_name = (settings_repo.get_app_setting("rag_collection") or "").strip() or None
        if use_rag and not collection_name:
            names = _get_qdrant_collection_names()
            if not names:
                return jsonify({
                    "error": "No Qdrant collections. Create one in Crawler / RAG then try again.",
                }), 400
            collection_name = names[0]

        # Defaults from config
        prompt_name = prompt_name or get_rag_prompt_name()

        params, deps = get_rag_answer_params(collection_name=collection_name)
        chat_client = deps.chat_client
        # Use selected model or fallback to config model
        ollama_model = model if model and model != "rag-ollama" else params.model_name
        
        last_user = last_user_content(messages)
        
        rag_chunks_info: list[dict[str, Any]] | None = None
        context_chars: int | None = None

        if use_rag:
            # Use RAG flow
            rag_repo = deps.rag_repo
            embed_provider = deps.embed_provider
            rerank_client = deps.rerank_client
            # Rerank on/off and model from model settings (default off)
            use_rerank_tester = False
            rerank_model_tester: str | None = None
            try:
                proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
                if proxy_settings_json:
                    proxy_settings = json.loads(proxy_settings_json)
                    use_rerank_tester = bool(proxy_settings.get("rerank_for_rag", False))
                    rm = (proxy_settings.get("rerank_model") or "").strip() or None
                    if rm:
                        rerank_model_tester = rm
            except Exception:
                pass
            if use_rerank_tester:
                effective_rerank_client = default_rerank_client(model=rerank_model_tester)
            else:
                effective_rerank_client = None
            
            prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
            
            context_length = len(last_user.split())
            if not reasoning_level:
                reasoning_level = determine_reasoning_level(
                    last_user, context_length, ollama_model, None
                )
            
            top_k_override = top_k if top_k is not None else None
            rag_keywords = _get_rag_required_keywords_from_module()
            trigger_threshold = _get_effective_rag_trigger_threshold()

            # Same as proxy: project_context -> fresh collection names and optional background refresh
            project_context = body.get("project_context") or (tester_settings.get("project_context") if tester_settings else None)
            project_fresh_collection_names: set[str] | None = None
            needs_refresh: list[tuple[str, str]] = []  # (framework_id_lower, collection_name); also filled from resolved below
            if (
                fetch_web_knowledge
                and isinstance(project_context, dict)
                and _EXTERNAL_DOCS_RAG_AVAILABLE
                and load_rag_sources_config
            ):
                frameworks = project_context.get("frameworks") or []
                if frameworks:
                    rag_sources_config = load_rag_sources_config()
                    name_to_collection: dict[str, str] = {}
                    for cfg in rag_sources_config:
                        for kw in (cfg.trigger_keywords or []):
                            name_to_collection[(kw or "").strip().lower()] = cfg.collection_name
                        if (cfg.external_source_id or "").strip():
                            name_to_collection[(cfg.external_source_id or "").strip().lower()] = cfg.collection_name
                    ttl_days = get_framework_collection_ttl_days()
                    ttl_repo = get_settings_repository()
                    try:
                        ttl_raw = ttl_repo.get_app_setting("framework_collection_ttl_days")
                        if ttl_raw is not None and str(ttl_raw).strip() != "":
                            try:
                                ttl_days = int(ttl_raw)
                            except (TypeError, ValueError):
                                pass
                    except Exception:
                        pass
                    fresh_collections: list[str] = []
                    needs_refresh.clear()
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
                        try:
                            meta = ttl_repo.get_collection_meta(coll)
                        except Exception:
                            pass
                        if check_collection_freshness(meta, ttl_days) == "fresh":
                            if coll not in fresh_collections:
                                fresh_collections.append(coll)
                        else:
                            needs_refresh.append((name.lower(), coll))
                    project_fresh_collection_names = set(fresh_collections) if fresh_collections else None

            # Same as proxy: body_rag_sources, resolve, build_merged_rag_context with fresh_collection_names
            use_merged = False
            if (
                fetch_web_knowledge
                and _EXTERNAL_DOCS_RAG_AVAILABLE
                and load_rag_sources_config
                and resolve_rag_sources_for_request
                and build_merged_rag_context
                and QdrantRagSearchAdapter is not None
            ):
                rag_sources_config = load_rag_sources_config()
                # When Fetch Web knowledge is on, resolve by triggers so frameworks (e.g. Alamofire) from the question are included; do not restrict to selected collection only
                body_rag_sources = None if fetch_web_knowledge else (body.get("rag_sources") or (tester_settings.get("rag_sources") if tester_settings else None))
                if isinstance(body_rag_sources, list):
                    body_rag_sources = [str(x) for x in body_rag_sources]
                else:
                    body_rag_sources = None
                resolved = resolve_rag_sources_for_request(last_user, messages, body_rag_sources, rag_sources_config)
                if len(resolved) >= 1:
                    use_merged = True
                    # Trigger full crawl for resolved sources that are missing or stale when repo is on GitHub (same as proxy)
                    try:
                        _settings_repo = get_settings_repository()
                        _ttl_days = get_framework_collection_ttl_days()
                        _ttl_raw = _settings_repo.get_app_setting("framework_collection_ttl_days")
                        if _ttl_raw is not None and str(_ttl_raw).strip() != "":
                            try:
                                _ttl_days = int(_ttl_raw)
                            except (TypeError, ValueError):
                                pass
                    except Exception:
                        _settings_repo = None
                        _ttl_days = 90
                    resolved_needs_refresh: list[tuple[str, str]] = []
                    if _settings_repo:
                        for cfg in resolved:
                            meta = None
                            try:
                                meta = _settings_repo.get_collection_meta(cfg.collection_name)
                            except Exception:
                                pass
                            if check_collection_freshness(meta, _ttl_days) != "fresh":
                                fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower() or cfg.collection_name.lower()
                                resolved_needs_refresh.append((fid, cfg.collection_name))
                    work_list = list(needs_refresh)
                    for (fid, coll) in resolved_needs_refresh:
                        if coll not in [c for _, c in work_list]:
                            work_list.append((fid, coll))
                    if work_list and load_github_repos and ingest_github_repo_markdown and HttpFetchClient and QdrantChunkSink and get_latest_release_tag:
                        coll_to_framework_id = {}
                        for cfg in rag_sources_config:
                            fid = (cfg.external_source_id or cfg.collection_name or "").strip().lower()
                            if fid:
                                coll_to_framework_id[cfg.collection_name] = fid
                        github_repos_list = load_github_repos()
                        by_framework_id = {(e.get("framework_id") or "").lower(): e for e in github_repos_list if e.get("framework_id")}

                        def _run_refresh(work: list) -> None:
                            try:
                                qdrant_url = get_qdrant_url()
                                fetch_client = HttpFetchClient()
                                chunk_sink = QdrantChunkSink(base_url=qdrant_url)
                                repo = get_settings_repository()
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
                                        tag = get_latest_release_tag(f"{owner}/{repo_name}")
                                        if tag:
                                            ref = tag
                                        else:
                                            ref = "main"
                                    ingest_github_repo_markdown(
                                        owner, repo_name, ref, coll, fid,
                                        fetch_client, chunk_sink, embed_provider,
                                        max_depth=3,
                                        on_indexed=on_indexed,
                                    )
                                    break
                            except Exception as e:
                                _WEBUI_LOG.warning("Background framework refresh failed: %s", e)

                        threading.Thread(target=_run_refresh, args=(work_list,), daemon=True).start()

                    try:
                        qdrant_url = get_qdrant_url()
                    except Exception:
                        qdrant_url = "http://localhost:6333"
                    rag_search_adapter = QdrantRagSearchAdapter(base_url=qdrant_url)
                    fetch_client = HttpFetchClient() if HttpFetchClient is not None else None
                    external_sources_list = load_external_sources() if load_external_sources else []
                    merged_ctx, merged_timings = build_merged_rag_context(
                        last_user,
                        resolved,
                        rag_search_adapter,
                        embed_provider,
                        params.context_chunk_chars,
                        params.context_total_chars,
                        fetch_client=fetch_client,
                        external_sources=external_sources_list,
                        fresh_collection_names=project_fresh_collection_names,
                    )
                    if merged_timings:
                        set_latest_request_rag_steps(merged_timings)
                    from domain.entities.rag import RagContext as AppRagContext
                    ctx = AppRagContext(
                        context_text=merged_ctx.context_text,
                        chunks_info=merged_ctx.chunks_info or [],
                        max_score=merged_ctx.max_score,
                    )
                    rag_chunks_info = ctx.chunks_info or None
                    context_chars = len(ctx.context_text) if ctx.context_text else None
            if not use_merged:
                ctx, rag_timings = build_rag_context(
                    last_user,
                    rag_repo,
                    embed_provider,
                    effective_rerank_client,
                    params.context_chunk_chars,
                    params.context_total_chars,
                    top_k=top_k_override,
                    rag_required_keywords=rag_keywords,
                    trigger_threshold=trigger_threshold,
                )
                if rag_timings:
                    set_latest_request_rag_steps(rag_timings)
                rag_chunks_info = ctx.chunks_info or None
                if rag_chunks_info:
                    context_chars = sum(int(c.get("text_length") or 0) for c in rag_chunks_info)
                else:
                    context_chars = None
            
            # Use the actual Ollama model name here; "rag-ollama" is the logical
            # OpenAI-compatible model id, not an Ollama model. Passing it here
            # causes 404 MODEL_NOT_FOUND from Ollama.
            req = RagQuestionRequest(
                messages=messages,
                model=ollama_model,
                stream=False,
                reasoning_level=reasoning_level,
            )
            
            ollama_messages, use_model = prepare_ollama_messages(
                req,
                rag_repo,
                embed_provider,
                effective_rerank_client,
                prefix,
                suffix,
                params.context_chunk_chars,
                params.context_total_chars,
                params.confidence_threshold,
                ollama_model,
                reasoning_level=reasoning_level,
                rag_required_keywords=rag_keywords,
                rag_context=ctx,
                trigger_threshold=trigger_threshold,
            )
            # Ensure use_model is not "rag-ollama" - use config model if needed
            if use_model == "rag-ollama":
                use_model = params.model_name
        else:
            # Direct chat without RAG
            use_model = ollama_model
            # Ensure use_model is not "rag-ollama" - use config model if needed
            if use_model == "rag-ollama":
                use_model = params.model_name
            ollama_messages = messages.copy()
            
            # Add system prompt if needed
            if prompt_name:
                prefix, _ = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
                if prefix:
                    ollama_messages.insert(0, {"role": "system", "content": prefix})
        
        # Prepare Ollama options
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = float(temperature)
        if top_p is not None:
            options["top_p"] = float(top_p)
        
        # Call chat
        content = chat_client.chat(
            ollama_messages,
            use_model,
            stream=False,
            options=options if options else None,
        )
        
        latency_ms = int((time.time() - start_time) * 1000)

        # Rough token accounting (approximate, for diagnostics / UX only)
        def _approx_tokens(text: str) -> int:
            # Simple heuristic: 1 token ≈ 4 characters
            if not text:
                return 0
            return max(1, int(len(text) / 4))

        prompt_text = " ".join((m.get("content") or "") for m in messages if isinstance(m, dict))
        prompt_tokens = _approx_tokens(prompt_text)
        completion_tokens = _approx_tokens(content or "")
        total_tokens = prompt_tokens + completion_tokens
        
        # Build response
        response_data: dict[str, Any] = {
            "id": f"chatcmpl-tester-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": use_model,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content or ""},
                "finish_reason": "stop",
            }],
        }

        if use_rag:
            response_data["rag_metadata"] = {
                "chunks_info": rag_chunks_info or [],
                "chunks_count": len(rag_chunks_info or []),
                "context_chars": context_chars,
            }
        
        return jsonify(response_data)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.tester_chat", exc_info=True)
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
        prompt_name = body.get("prompt_name") or get_rag_prompt_name()
        swift_mode = body.get("swift_mode", "default")
        user_message = body.get("user_message") or ""
        use_rag = bool(body.get("use_rag", True))

        # Base system template for the selected prompt + Swift mode
        prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)

        # Build a representative system message using the same logic as runtime chat,
        # but with a lightweight placeholder instead of real RAG context.
        try:
            confidence_threshold = get_rag_float("confidence_threshold", 0.75)
        except Exception:
            confidence_threshold = 0.75
        try:
            model_name = get_ollama_chat_model()
        except Exception:
            model_name = "rag-ollama"

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
                "swift_mode": swift_mode,
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
    url = get_qdrant_url().rstrip("/")
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        resp = requests.get(f"{url}/collections", timeout=3)
        status["http_status"] = resp.status_code
        if resp.ok:
            data = resp.json() or {}
            collections = data.get("result", {}).get("collections", [])
            status["running"] = True
            status["collections_count"] = len(collections)
        try:
            version_resp = requests.get(f"{url}/cluster", timeout=3)
            if version_resp.ok:
                vdata = version_resp.json() or {}
                status["version"] = vdata.get("result", {}).get("status", {}).get("version")
        except Exception:
            pass
    except Exception as e:
        status["error"] = str(e)
        _WEBUI_LOG.warning(f"Failed to get Qdrant status: {e}")
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
    url_q = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url_q}/collections", timeout=3)
        if resp.ok:
            data = resp.json() or {}
            collections = data.get("result", {}).get("collections", [])
            payload["rag"] = {"running": True, "collections_count": len(collections)}
        else:
            payload["rag"] = {"running": False, "collections_count": 0}
    except Exception:
        payload["rag"] = {"running": False, "collections_count": 0}
    url_o = _get_ollama_url().rstrip("/")
    try:
        r = requests.get(f"{url_o}/api/tags", timeout=3)
        payload["ollama"] = {"running": r.ok}
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
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=5)
        if not resp.ok:
            return []
        data = resp.json() or {}
        raw = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw:
            name = col.get("name") if isinstance(col, dict) else str(col)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


@webui_bp.route("/rag/collections", methods=["GET"])
def rag_collections() -> Any:
    """Return detailed information about Qdrant collections."""
    url = get_qdrant_url().rstrip("/")
    try:
        # First get list of collections via HTTP API
        resp = requests.get(f"{url}/collections", timeout=5)
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

        # TTL and default top_k (app_settings override config)
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

        return jsonify({
            "collections": detailed,
            "ttl_days": ttl_days,
            "default_rag_top_k": default_top_k,
        })
    except Exception as e:
        _WEBUI_LOG.error("Failed to get Qdrant collections: %s", e, exc_info=True)
        return jsonify({"collections": [], "error": str(e)}), 500


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


def _run_docker_command(args: list[str]) -> tuple[bool, str]:
    """Helper to run docker commands (best-effort, may fail safely)."""
    try:
        proc = run(
            ["docker", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        ok = proc.returncode == 0
        output = proc.stdout.strip() or proc.stderr.strip()
        return ok, output
    except Exception as e:
        return False, str(e)


def _get_qdrant_container_name() -> str:
    return os.getenv("QDRANT_CONTAINER_NAME", "qdrant")


@webui_bp.route("/rag/start", methods=["POST"])
def rag_start() -> Any:
    """Try to start Qdrant Docker container."""
    name = _get_qdrant_container_name()
    ok, output = _run_docker_command(["start", name])
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output, "container": name}), status


@webui_bp.route("/rag/stop", methods=["POST"])
def rag_stop() -> Any:
    """Try to stop Qdrant Docker container."""
    name = _get_qdrant_container_name()
    ok, output = _run_docker_command(["stop", name])
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output, "container": name}), status


def _get_open_webui_container_name() -> str:
    return os.getenv("OPEN_WEBUI_CONTAINER_NAME", "open-webui")


def _get_open_webui_url() -> str:
    return os.getenv("OPEN_WEBUI_URL", "http://localhost:3000").rstrip("/")


def _is_open_webui_container_running() -> bool:
    """Return True if a Docker container whose name matches OPEN_WEBUI_CONTAINER_NAME is running (docker ps)."""
    name = _get_open_webui_container_name()
    try:
        # --filter name=NAME matches if container name contains NAME (e.g. "open-webui" or "open-webui-open-webui-1")
        proc = run(
            ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return False
        out = (proc.stdout or "").strip()
        # One or more lines; accept if our name appears (exact or as part of compose-style name)
        if not out:
            return False
        for line in out.splitlines():
            line = line.strip()
            if line == name or name in line or line.endswith(name):
                return True
        return False
    except Exception:
        return False


def open_webui_status() -> Any:
    """Return Open WebUI status from Docker: running if container matching OPEN_WEBUI_CONTAINER_NAME is up."""
    url = _get_open_webui_url()
    status: dict[str, Any] = {"url": url, "running": False}
    if _is_open_webui_container_running():
        status["running"] = True
        status["detected_by"] = "docker"
    try:
        resp = requests.get(url, timeout=2)
        status["http_status"] = resp.status_code
    except Exception as e:
        status["http_error"] = str(e)
    return jsonify(status)


def open_webui_start() -> Any:
    """Try to start Open WebUI Docker container."""
    name = _get_open_webui_container_name()
    ok, output = _run_docker_command(["start", name])
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output, "container": name}), status


def open_webui_stop() -> Any:
    """Try to stop Open WebUI Docker container."""
    name = _get_open_webui_container_name()
    ok, output = _run_docker_command(["stop", name])
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output, "container": name}), status


def _get_ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


@webui_bp.route("/ollama/status", methods=["GET"])
def ollama_status() -> Any:
    """Check if Ollama server is reachable on port 11434 (or OLLAMA_URL)."""
    url = _get_ollama_url().rstrip("/")
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        resp = requests.get(f"{url}/api/tags", timeout=3)
        status["http_status"] = resp.status_code
        if resp.ok:
            status["running"] = True
    except Exception as e:
        status["error"] = str(e)
        _WEBUI_LOG.warning(f"Failed to get Ollama status: {e}")
    return jsonify(status)


def _start_ollama_process() -> tuple[bool, str]:
    """Best-effort start of ollama serve as background process."""
    try:
        # Cross-platform detached process
        kwargs: dict[str, Any] = {"stdout": None, "stderr": None}
        if os.name == "nt":
            # Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        Popen(["ollama", "serve"], **kwargs)
        return True, "ollama serve started"
    except Exception as e:
        return False, str(e)


def _stop_ollama_process() -> tuple[bool, str]:
    """
    Best-effort stop of Ollama server.

    On Windows uses taskkill; on POSIX uses pkill. If commands are not available,
    this will fail gracefully.
    """
    try:
        if os.name == "nt":
            proc = run(
                ["taskkill", "/IM", "ollama.exe", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            proc = run(
                ["pkill", "-f", "ollama"],
                capture_output=True,
                text=True,
                check=False,
            )
        ok = proc.returncode == 0
        output = proc.stdout.strip() or proc.stderr.strip()
        return ok, output or "ok" if ok else "failed"
    except Exception as e:
        return False, str(e)


@webui_bp.route("/ollama/start", methods=["POST"])
def ollama_start() -> Any:
    """Try to start Ollama server (ollama serve)."""
    ok, output = _start_ollama_process()
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output}), status


@webui_bp.route("/ollama/stop", methods=["POST"])
def ollama_stop() -> Any:
    """Try to stop Ollama server process."""
    ok, output = _stop_ollama_process()
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output}), status


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
    dirty_pages = sum(1 for p in pages.values() if p.get("dirty", False))
    indexed_pages = sum(
        1 for p in pages.values() 
        if p.get("chunk_hashes") and len(p.get("chunk_hashes", [])) > 0
    )
    return {
        "total_pages": total_pages,
        "dirty_pages": dirty_pages,
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


def _get_embeddings_simple(texts: list[str]) -> list[list[float]]:
    """Simple embedding function using Ollama."""
    if not texts:
        return []
    
    embed_url = get_ollama_embed_url()
    embed_model = os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")
    
    try:
        response = requests.post(
            embed_url,
            json={"model": embed_model, "input": texts},
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError(f"Expected {len(texts)} embeddings, got {len(embeddings)}")
        return embeddings
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to get embeddings: {e}")
        raise


def _strip_markdown_simple(md: str) -> str:
    """Simple markdown cleaning - remove excessive whitespace."""
    if not md:
        return ""
    # Remove excessive newlines
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _ensure_collection_with_name(qclient: QdrantClient, collection_name: str, dim: int) -> None:
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
    
    # Create collection
    try:
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


def _create_collection_from_sources(
    collection_name: str,
    source_ids: list[str],
    chunk_max_size: int,
    chunk_min_size: int,
    on_progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Create a Qdrant collection by indexing pages from specified sources.
    Returns statistics about the indexing process.
    If on_progress is set, called as on_progress(processed_count, total_pages, stats) after each page.
    """
    sources_dir = _get_crawler_sources_dir()
    qdrant_url = get_qdrant_url().rstrip("/")
    qclient = QdrantClient(url=qdrant_url)
    
    stats = {
        "total_pages": 0,
        "indexed_pages": 0,
        "total_chunks": 0,
        "skipped_pages": 0,
        "errors": [],
    }
    
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
        page_path = os.path.join(pages_dir, filename)
        
        try:
            with open(page_path, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception as e:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Failed to read {source_id}/{filename}: {e}")
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        page_meta, md = parse_and_strip_meta_block(md)
        # Simple validation - skip if too short
        if len(md.strip()) < 400:
            stats["skipped_pages"] += 1
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        # Clean markdown
        md = _strip_markdown_simple(md)

        # Split into chunks
        try:
            chunks_with_paths = split_markdown_into_chunks(
                md, max_chunk_size=chunk_max_size, min_chunk_size=chunk_min_size
            )
            chunks_with_paths = [(t, p) for t, p in chunks_with_paths if chunk_quality_ok(t)]
        except Exception as e:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Failed to chunk {source_id}/{filename}: {e}")
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        if not chunks_with_paths:
            stats["skipped_pages"] += 1
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        chunk_texts = [t for t, _ in chunks_with_paths]
        embed_texts = [
            build_embed_prefix(page_meta, sp) + t
            for t, sp in chunks_with_paths
        ]

        # Get embeddings
        try:
            embeddings = _get_embeddings_simple(embed_texts)
        except Exception as e:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Failed to get embeddings for {source_id}/{filename}: {e}")
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        if not embeddings:
            stats["skipped_pages"] += 1
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue

        dim = len(embeddings[0])
        if first_dim is None:
            first_dim = dim
            _ensure_collection_with_name(qclient, collection_name, first_dim)

        if dim != first_dim:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Dimension mismatch for {source_id}/{filename}: {dim} != {first_dim}")
            processed += 1
            if on_progress:
                on_progress(processed, total_pages, dict(stats))
            continue
        
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
            payload = {
                "source": source_id,
                "url": url_for_meta or entry.get("url", ""),
                "path": f"pages/{filename}",
                "chunk_id": chunk_hash,
                "text": chunk_text,
                "section_path": section_path,
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
                    vector=vec,
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
        if on_progress:
            on_progress(processed, total_pages, dict(stats))
    
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
                "dirty_pages": stats["dirty_pages"],
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
                "dirty_pages": 0,
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
                "dirty": page_data.get("dirty", False),
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
    use_model = model if model and model != "rag-ollama" else params.model_name
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
    use_model = model if model and model != "rag-ollama" else (params.model_name if params else None)
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
        proc = subprocess.Popen(
            [sys.executable, app_path, "crawl", "--source", source_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(app_path),
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
        from pathlib import Path
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
        from pathlib import Path
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
) -> None:
    """Background task: run indexing and update job progress."""
    def on_progress(processed: int, total: int, st: dict[str, Any]) -> None:
        with _collection_jobs_lock:
            if job_id in _collection_jobs:
                _collection_jobs[job_id]["processed_pages"] = processed
                _collection_jobs[job_id]["total_pages"] = total
                _collection_jobs[job_id]["indexed_pages"] = st.get("indexed_pages", 0)
                _collection_jobs[job_id]["total_chunks"] = st.get("total_chunks", 0)
                _collection_jobs[job_id]["skipped_pages"] = st.get("skipped_pages", 0)
                _collection_jobs[job_id]["errors"] = list(st.get("errors", [])[-5:])

    try:
        stats = _create_collection_from_sources(
            collection_name=collection_name,
            source_ids=source_ids,
            chunk_max_size=chunk_max_size,
            chunk_min_size=chunk_min_size,
            on_progress=on_progress,
        )
        with _collection_jobs_lock:
            if job_id in _collection_jobs:
                _collection_jobs[job_id]["status"] = "success"
                _collection_jobs[job_id]["statistics"] = stats
                _collection_jobs[job_id]["processed_pages"] = stats.get("total_pages", 0)
                _collection_jobs[job_id]["indexed_pages"] = stats.get("indexed_pages", 0)
                _collection_jobs[job_id]["total_chunks"] = stats.get("total_chunks", 0)
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
        "processed_pages": job.get("processed_pages", 0),
        "total_pages": job.get("total_pages", 0),
        "indexed_pages": job.get("indexed_pages", 0),
        "total_chunks": job.get("total_chunks", 0),
        "skipped_pages": job.get("skipped_pages", 0),
        "errors": job.get("errors", []),
        "statistics": job.get("statistics"),
        "error": job.get("error"),
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
        confidence_threshold = float(body.get("confidence_threshold", 0.75))
        top_k = int(body.get("top_k", 4))

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

        sources_dir = _get_crawler_sources_dir()
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
                "processed_pages": 0,
                "total_pages": total_pages,
                "indexed_pages": 0,
                "total_chunks": 0,
                "skipped_pages": 0,
                "errors": [],
            }

        thread = threading.Thread(
            target=_run_create_collection_job,
            args=(job_id, collection_name, available_sources, chunk_max_size, chunk_min_size),
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


# ----- RAG Tests (Markdown-defined tests, run against proxy, validate concepts + RAG) -----
# In-memory job store for async run with progress and cancel
_rag_test_jobs: dict[str, dict[str, Any]] = {}
_rag_test_jobs_lock = threading.Lock()


def _get_rag_tests_module():
    try:
        from application.rag_tests.loader import (
            get_rag_tests_root,
            list_test_filters,
            load_all_tests,
            load_test,
        )
        from application.rag_tests.validator import validate_result
        return get_rag_tests_root, list_test_filters, load_all_tests, load_test, validate_result
    except ImportError:
        return None, None, None, None, None


@webui_bp.route("/rag-tests", methods=["GET"])
def rag_tests_list() -> Any:
    """List all RAG tests, optionally filtered by platform, framework, difficulty."""
    get_root, list_filters, load_all, load_one, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = get_root()
    tests = load_all(root)
    platform = (request.args.get("platform") or "").strip()
    framework = (request.args.get("framework") or "").strip()
    difficulty = (request.args.get("difficulty") or "").strip()
    if platform:
        tests = [t for t in tests if (t.get("platform") or "") == platform]
    if framework:
        tests = [t for t in tests if (t.get("framework") or "") == framework]
    if difficulty:
        tests = [t for t in tests if (t.get("difficulty") or "") == difficulty]
    filters = list_filters(tests) if list_filters else {"platform": [], "framework": [], "difficulty": []}
    return jsonify({"tests": tests, "filters": filters})


@webui_bp.route("/rag-tests/filters", methods=["GET"])
def rag_tests_filters() -> Any:
    """Return distinct platform, framework, difficulty for filter dropdowns."""
    _, list_filters, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = _get_rag_tests_module()[0]()
    tests = load_all(root)
    filters = list_filters(tests) if list_filters else {"platform": [], "framework": [], "difficulty": []}
    return jsonify(filters)


@webui_bp.route("/rag-tests/runs", methods=["GET"])
def rag_tests_runs_list() -> Any:
    """List past RAG test runs (history). Query: limit, offset, model, from_date, to_date, status."""
    try:
        repo = get_rag_test_runs_repository()
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = max(0, int(request.args.get("offset", 0)))
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        status = (request.args.get("status") or "").strip() or None
        runs = repo.get_runs(
            limit=limit,
            offset=offset,
            model=model,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )
        return jsonify({"runs": runs})
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_runs_list")
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-tests/runs/summary", methods=["GET"])
def rag_tests_runs_summary() -> Any:
    """Aggregate metrics for runs. Query: limit (default 50), model, from_date, to_date."""
    try:
        repo = get_rag_test_runs_repository()
        limit = min(int(request.args.get("limit", 50)), 200)
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        summary = repo.get_runs_summary(
            limit=limit,
            model=model,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify(summary)
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_runs_summary")
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-tests/runs/<run_id>", methods=["GET"])
def rag_tests_run_detail(run_id: str) -> Any:
    """Get a single past run with full results. Query param format=csv returns CSV attachment."""
    export_format = (request.args.get("format") or "").strip().lower()
    if export_format == "csv":
        return _rag_tests_export_run(run_id, "csv")
    try:
        repo = get_rag_test_runs_repository()
        run = repo.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(run)
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_run_detail")
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/rag-tests/runs/<run_id>/export", methods=["GET"])
def rag_tests_run_export(run_id: str) -> Any:
    """Export run as JSON or CSV attachment. Query param format=csv|json (default json)."""
    export_format = (request.args.get("format") or "json").strip().lower()
    if export_format not in ("json", "csv"):
        export_format = "json"
    return _rag_tests_export_run(run_id, export_format)


def _rag_tests_export_run(run_id: str, export_format: str) -> Any:
    """Return run data as JSON or CSV with Content-Disposition."""
    try:
        repo = get_rag_test_runs_repository()
        run = repo.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_export_run")
        return jsonify({"error": str(e)}), 500
    created = run.get("created_at") or ""
    safe_date = created.replace(":", "-").replace(" ", "_")[:19] if created else "run"
    filename = f"rag-test-run-{run_id}-{safe_date}.{export_format}"
    if export_format == "csv":
        import csv
        import io
        rows = [["test_id", "test_name", "platform", "framework", "status", "response_time_ms", "rag_used", "confidence_label", "question", "error"]]
        for r in (run.get("results") or []):
            rows.append([
                r.get("test_id") or "",
                r.get("test_name") or "",
                r.get("platform") or "",
                r.get("framework") or "",
                r.get("status") or "",
                str(r.get("response_time_ms") or ""),
                "yes" if r.get("rag_used") else "no",
                r.get("confidence_label") or "",
                (r.get("question") or "").replace("\r", " ").replace("\n", " "),
                r.get("error") or "",
            ])
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerows(rows)
        body = buf.getvalue()
        resp = Response(body, mimetype="text/csv")
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    # JSON
    body = json.dumps(run, indent=2)
    resp = Response(body, mimetype="application/json")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _rag_tests_find_by_id(get_root: Any, load_all: Any, test_id: str) -> dict[str, Any] | None:
    """Return test dict with absolute_path if found, else None."""
    if load_all is None:
        return None
    root = Path(get_root())
    tests = load_all(root)
    for t in tests:
        if t.get("id") == test_id:
            return t
    return None


def _normalize_concepts(raw_concepts: list[str]) -> list[str]:
    """
    Normalize Expected Concepts coming from the WebUI/CLI.

    Rules:
    - One atomic concept per entry (no combined lists like `weak / unowned`).
    - Trim whitespace and drop empty entries.
    - Split on common separators (`/`, `,`, `;`, ` and `) when they clearly
      represent multiple concepts, for example:
        - \"weak / unowned\" -> [\"weak\", \"unowned\"]
        - \"weak and unowned\" -> [\"weak\", \"unowned\"]
    - If the string still looks ambiguous after splitting (mixture of
      separators, very long phrase), keep it as-is so the author can fix it.
    """
    normalized: list[str] = []
    for item in raw_concepts:
        text = (item or "").strip()
        if not text:
            continue

        lowered = text.lower()
        # Fast path: no obvious separators, treat as a single concept.
        if all(sep not in lowered for sep in ("/", ",", ";", " and ")):
            normalized.append(text)
            continue

        # Handle the most common simple patterns safely.
        # Priority: explicit " and " between two short tokens, or slash/comma-separated tokens.
        candidates: list[str] = []

        def _split_and_extend(separator: str) -> None:
            parts = [p.strip() for p in text.split(separator) if p.strip()]
            if len(parts) >= 2:
                candidates.extend(parts)

        # Try word-level conjunction first.
        if " and " in lowered:
            _split_and_extend(" and ")
        # Then symbol-based separators.
        if "/" in text:
            _split_and_extend("/")
        if "," in text:
            _split_and_extend(",")
        if ";" in text:
            _split_and_extend(";")

        # Heuristic: if we obtained at least two reasonably short pieces and
        # the combined length is similar to the original, treat them as
        # separate atomic concepts. Otherwise, keep the original string so
        # that the test author can adjust it explicitly.
        if len(candidates) >= 2 and all(len(c) <= 40 for c in candidates):
            for c in candidates:
                if c and c not in normalized:
                    normalized.append(c)
            continue

        normalized.append(text)

    return normalized


def _rag_tests_build_md(
    name: str,
    question: str,
    concepts: list[str],
    platform: str,
    framework: str,
    difficulty: str,
    concept_mode: str,
    rag_strict: bool,
    min_os: str,
    notes: str,
) -> str:
    """Build .md file content for create/update."""
    lines = [
        f"# {name}",
        "",
        f"Platform: {platform}",
        f"Framework: {framework}",
        f"Difficulty: {difficulty}",
        f"Concept Mode: {concept_mode}",
    ]
    if rag_strict:
        lines.append("RAG Strict: true")
    if min_os:
        lines.append(f"MinOS: {min_os}")
    lines.extend(["", "## Question", "", question, "", "## Expected Concepts", ""])
    for c in concepts:
        lines.append(f"- {c}")
    lines.extend(["", "## RAG Requirement", "", "The answer must reference retrieved documentation or RAG context.", ""])
    if notes:
        lines.extend(["## Notes", "", notes])
    return "\n".join(lines)


@webui_bp.route("/rag-tests/<test_id>", methods=["GET"])
def rag_tests_get_one(test_id: str) -> Any:
    """Get a single RAG test by id (path-based id)."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = get_root()
    tests = load_all(root)
    for t in tests:
        if t.get("id") == test_id:
            return jsonify(t)
    return jsonify({"error": "Test not found"}), 404


@webui_bp.route("/rag-tests/<test_id>", methods=["PUT"])
def rag_tests_update(test_id: str) -> Any:
    """Update an existing RAG test. Body same as create. Overwrites the .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    t = _rag_tests_find_by_id(get_root, load_all, test_id)
    if not t:
        return jsonify({"error": "Test not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or body.get("question") or "Untitled test")[:200].strip()
    question = (body.get("question") or "").strip()
    concepts = body.get("concepts") or body.get("expected_concepts") or []
    if isinstance(concepts, str):
        concepts = [c.strip() for c in concepts.split("\n") if c.strip()]
    concepts = _normalize_concepts(list(concepts))
    platform = (body.get("platform") or "iOS").strip()
    framework = (body.get("framework") or "SwiftUI").strip()
    difficulty = (body.get("difficulty") or "intermediate").strip()
    concept_mode = (body.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    rag_strict = bool(body.get("rag_strict"))
    min_os = (body.get("min_os") or "").strip()
    notes = (body.get("notes") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    path = Path(t["absolute_path"])
    content = _rag_tests_build_md(
        name, question, concepts, platform, framework, difficulty, concept_mode, rag_strict, min_os, notes
    )
    path.write_text(content, encoding="utf-8")
    return jsonify({"id": test_id, "message": "Test updated"}), 200


@webui_bp.route("/rag-tests/<test_id>", methods=["DELETE"])
def rag_tests_delete(test_id: str) -> Any:
    """Delete a RAG test by removing its .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    t = _rag_tests_find_by_id(get_root, load_all, test_id)
    if not t:
        return jsonify({"error": "Test not found"}), 404
    path = Path(t["absolute_path"])
    if path.exists():
        path.unlink()
    return "", 204


def _rag_tests_run_worker(
    job_id: str,
    app_context: Any,
    tests_to_run: list[dict[str, Any]],
    model: str,
    collection_name: str,
    prompt_name: str | None = None,
) -> None:
    """Background worker: run tests one by one, update job progress, respect cancel."""
    with app_context:
        client = current_app.test_client()
        get_root, _, _, _, validate_result = _get_rag_tests_module()
        if validate_result is None:
            with _rag_test_jobs_lock:
                _rag_test_jobs[job_id]["status"] = "completed"
                _rag_test_jobs[job_id]["error"] = "RAG tests module not available"
            return
        total = len(tests_to_run)
        results: list[dict[str, Any]] = []
        passed = 0
        failed = 0
        for i, test in enumerate(tests_to_run):
            with _rag_test_jobs_lock:
                if _rag_test_jobs.get(job_id, {}).get("cancel_requested"):
                    _rag_test_jobs[job_id]["status"] = "cancelled"
                    _rag_test_jobs[job_id]["progress"]["pending"] = total - i
                    break
                _rag_test_jobs[job_id]["progress"] = {
                    "current_index": i + 1,
                    "total": total,
                    "current_test_name": test.get("name") or test.get("id") or "",
                    "passed": passed,
                    "failed": failed,
                    "pending": total - i - 1,
                }
                _rag_test_jobs[job_id]["results"] = list(results)
            question = test.get("question") or ""
            start_time = time.time()
            try:
                chat_payload: dict[str, Any] = {
                    "messages": [{"role": "user", "content": question}],
                    "model": model,
                    "include_rag_metadata": True,
                    "collection_name": collection_name,
                    # Force RAG for test runs to validate retrieval and strict overlap
                    "force_rag": True,
                }
                if prompt_name:
                    chat_payload["prompt_name"] = prompt_name
                resp = client.post("/api/webui/chat", json=chat_payload)
                elapsed_ms = int((time.time() - start_time) * 1000)
                if resp.status_code != 200:
                    data = resp.get_json(silent=True) or {}
                    err = data.get("error", resp.get_data(as_text=True))
                    result = {
                        "test_id": test.get("id"),
                        "test_name": test.get("name"),
                        "platform": test.get("platform"),
                        "framework": test.get("framework"),
                        "model": model,
                        "status": "FAIL",
                        "response_time_ms": elapsed_ms,
                        "latency_ms": elapsed_ms,
                        "rag_used": False,
                        "confidence_label": "0/0",
                        "missing_concepts": test.get("expected_concepts") or [],
                        "found_concepts": [],
                        "full_response": None,
                        "chunks_info": [],
                        "retrieved_chunks": None,
                        "question": question,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "context_chars": None,
                        "failure_reason": str(err),
                        "error": str(err),
                    }
                    results.append(result)
                    failed += 1
                    continue
                data = resp.get_json(silent=True) or {}
                choices = data.get("choices") or []
                content = (choices[0].get("message") or {}).get("content", "") if choices else ""
                rag_metadata = data.get("rag_metadata") or {}
                usage = data.get("usage") or {}
                latency_ms = data.get("latency_ms") or rag_metadata.get("latency_ms") or elapsed_ms
                validation = validate_result(test, content, rag_metadata)
                result = {
                    "test_id": test.get("id"),
                    "test_name": test.get("name"),
                    "platform": test.get("platform"),
                    "framework": test.get("framework"),
                    "model": model,
                    "status": validation.get("status", "FAIL"),
                    "response_time_ms": elapsed_ms,
                    "latency_ms": latency_ms,
                    "rag_used": validation.get("rag_used", False),
                    "confidence_label": validation.get("confidence_label", ""),
                    "missing_concepts": validation.get("missing_concepts") or [],
                    "found_concepts": validation.get("found_concepts") or [],
                    "full_response": content or None,
                    "chunks_info": rag_metadata.get("chunks_info") or [],
                    "retrieved_chunks": validation.get("retrieved_chunks"),
                    "question": question,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "context_chars": rag_metadata.get("context_chars"),
                }
                if validation.get("failure_reason") is not None:
                    result["failure_reason"] = validation["failure_reason"]
                results.append(result)
                if result.get("status") == "PASS":
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                _ERROR_LOG.exception("rag_tests_run single test")
                _elapsed = int((time.time() - start_time) * 1000)
                results.append({
                    "test_id": test.get("id"),
                    "test_name": test.get("name"),
                    "platform": test.get("platform"),
                    "framework": test.get("framework"),
                    "model": model,
                    "status": "FAIL",
                    "response_time_ms": _elapsed,
                    "latency_ms": _elapsed,
                    "rag_used": False,
                    "confidence_label": "0/0",
                    "missing_concepts": test.get("expected_concepts") or [],
                    "found_concepts": [],
                    "full_response": None,
                    "chunks_info": [],
                    "retrieved_chunks": None,
                    "question": question,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "context_chars": None,
                    "failure_reason": str(e),
                    "error": str(e),
                })
                failed += 1
        with _rag_test_jobs_lock:
            if job_id in _rag_test_jobs and _rag_test_jobs[job_id]["status"] == "running":
                _rag_test_jobs[job_id]["status"] = "completed"
            _rag_test_jobs[job_id]["progress"]["passed"] = passed
            _rag_test_jobs[job_id]["progress"]["failed"] = failed
            _rag_test_jobs[job_id]["progress"]["pending"] = max(0, total - len(results))
            _rag_test_jobs[job_id]["results"] = results
        try:
            runs_repo = get_rag_test_runs_repository()
            status = _rag_test_jobs.get(job_id, {}).get("status", "completed")
            runs_repo.add_run(
                run_id=job_id,
                model=model,
                status=status,
                total=total,
                passed=passed,
                failed=failed,
                results=results,
            )
        except Exception as e:
            _ERROR_LOG.warning("Failed to persist RAG test run: %s", e)


@webui_bp.route("/rag-tests/run", methods=["POST"])
def rag_tests_run() -> Any:
    """Start RAG test run in background. Returns 202 with job_id. Poll GET /rag-tests/run/status/<job_id> for progress."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    body = request.get_json(force=True, silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    test_ids = body.get("test_ids")
    filter_obj = body.get("filter") or {}
    root = get_root()
    all_tests = load_all(root)
    if test_ids:
        by_id = {t["id"]: t for t in all_tests}
        tests_to_run = [by_id[tid] for tid in test_ids if tid in by_id]
    elif filter_obj:
        tests_to_run = all_tests
        if filter_obj.get("platform"):
            tests_to_run = [t for t in tests_to_run if (t.get("platform") or "") == filter_obj["platform"]]
        if filter_obj.get("framework"):
            tests_to_run = [t for t in tests_to_run if (t.get("framework") or "") == filter_obj["framework"]]
        if filter_obj.get("difficulty"):
            tests_to_run = [t for t in tests_to_run if (t.get("difficulty") or "") == filter_obj["difficulty"]]
    else:
        tests_to_run = all_tests
    if not tests_to_run:
        return jsonify({"results": [], "message": "No tests to run"})
    collection_name = (body.get("collection_name") or "").strip()
    if not collection_name:
        names = _get_qdrant_collection_names()
        if not names:
            return jsonify({
                "error": "No Qdrant collections. Create one in Crawler / RAG then come back.",
            }), 400
        collection_name = names[0]
    prompt_name = (body.get("prompt_name") or "").strip() or None
    job_id = str(uuid.uuid4())[:12]
    with _rag_test_jobs_lock:
        _rag_test_jobs[job_id] = {
            "status": "running",
            "cancel_requested": False,
            "progress": {
                "current_index": 0,
                "total": len(tests_to_run),
                "current_test_name": "",
                "passed": 0,
                "failed": 0,
                "pending": len(tests_to_run),
            },
            "results": [],
            "error": None,
        }
    thread = threading.Thread(
        target=_rag_tests_run_worker,
        args=(job_id, current_app.app_context(), tests_to_run, model, collection_name, prompt_name),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "collection_name": collection_name, "prompt_name": prompt_name}), 202


@webui_bp.route("/rag-tests/run/status/<job_id>", methods=["GET"])
def rag_tests_run_status(job_id: str) -> Any:
    """Get run progress and results. status: running | completed | cancelled."""
    with _rag_test_jobs_lock:
        job = _rag_test_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "results": job["results"],
        "error": job.get("error"),
    })


@webui_bp.route("/rag-tests/run/cancel/<job_id>", methods=["POST"])
def rag_tests_run_cancel(job_id: str) -> Any:
    """Request cancel; runner will stop after current test."""
    with _rag_test_jobs_lock:
        job = _rag_test_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "running":
        return jsonify({"message": "Job not running", "status": job["status"]})
    with _rag_test_jobs_lock:
        _rag_test_jobs[job_id]["cancel_requested"] = True
    return jsonify({"message": "Cancel requested", "job_id": job_id})


@webui_bp.route("/rag-tests", methods=["POST"])
def rag_tests_create() -> Any:
    """Create a new RAG test: body { name, question, concepts[], platform, framework, difficulty, concept_mode?, min_os?, notes? }. Writes .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if get_root is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or body.get("question") or "Untitled test")[:200].strip()
    question = (body.get("question") or "").strip()
    concepts = body.get("concepts") or body.get("expected_concepts") or []
    if isinstance(concepts, str):
        concepts = [c.strip() for c in concepts.split("\n") if c.strip()]
    concepts = _normalize_concepts(list(concepts))
    platform = (body.get("platform") or "iOS").strip()
    framework = (body.get("framework") or "SwiftUI").strip()
    difficulty = (body.get("difficulty") or "intermediate").strip()
    concept_mode = (body.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    rag_strict = bool(body.get("rag_strict"))
    min_os = (body.get("min_os") or "").strip()
    notes = (body.get("notes") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    # Slug from name or first line of question
    slug = re.sub(r"[^\w\s-]", "", name).strip()
    slug = re.sub(r"[-\s]+", "_", slug).lower()[:80] or "test"
    root = Path(get_root())
    platform_dir = root / platform.lower().replace(" ", "_")
    framework_dir = platform_dir / framework.lower().replace(" ", "_")
    framework_dir.mkdir(parents=True, exist_ok=True)
    path = framework_dir / f"{slug}.md"
    if path.exists():
        n = 1
        while (framework_dir / f"{slug}_{n}.md").exists():
            n += 1
        path = framework_dir / f"{slug}_{n}.md"
        slug = f"{slug}_{n}"
    content = _rag_tests_build_md(
        name, question, concepts, platform, framework, difficulty, concept_mode, rag_strict, min_os, notes
    )
    path.write_text(content, encoding="utf-8")
    test_id = str(path.relative_to(root)).replace(".md", "").replace("/", "_").replace("\\", "_")
    return jsonify({"id": test_id, "file_path": str(path.relative_to(root)), "message": "Test created"}), 201


__all__ = ["webui_bp"]

