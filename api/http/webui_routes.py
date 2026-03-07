"""
Flask routes for WebUI frontend.

Exposes /api/webui/* endpoints for models, prompts, logs, chat, and config.
Provides enhanced chat endpoint with RAG metadata and in-memory request buffer for dev console.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from subprocess import run, Popen
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from application.rag.params import RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from config import get_ollama_chat_model, get_qdrant_url, get_rag_float, get_rag_int, get_rag_prompt_name
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
from domain.entities.rag import RagQuestionRequest
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.database import get_session_manager, get_logs_repository, get_settings_repository
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
from domain.services.metadata_inference import extract_versions, infer_metadata

# Import config for embeddings
try:
    from config import get_ollama_embed_url, get_indexing_int
except ImportError:
    get_ollama_embed_url = lambda: "http://localhost:11434/api/embed"  # type: ignore
    get_indexing_int = lambda k, d: d  # type: ignore

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess

# In-memory buffer for dev console (last 50 requests)
_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

webui_bp = Blueprint("webui", __name__, url_prefix="/api/webui")


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
        
        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id="proxy",
            level="INFO",
            limit=limit,
            since_id=int(since_id) if since_id else None,
            source="proxy",
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
        
        # Get collection name from request or settings
        collection_name = body.get("collection_name")
        if not collection_name:
            settings_repo = get_settings_repository()
            collection_name = settings_repo.get_app_setting("rag_collection")
            if collection_name == "":
                collection_name = None
        
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
        
        # Rerank on/off from model settings (default off)
        use_rerank = False
        try:
            settings_repo = get_settings_repository()
            proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
            if proxy_settings_json:
                proxy_settings = json.loads(proxy_settings_json)
                use_rerank = bool(proxy_settings.get("rerank_for_rag", False))
        except Exception:
            pass
        effective_rerank_client = rerank_client if use_rerank else None
        
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
        ctx, rag_timings = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            effective_rerank_client,
            params.context_chunk_chars,
            params.context_total_chars,
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
        )
        # Ensure use_model is not "rag-ollama" - use config model if needed
        if use_model == "rag-ollama":
            use_model = params.model_name
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
        set_latest_request_total_tokens(max(1, int(len(_pt) / 4)) + max(1, int(len(content or "") / 4)))
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Build response
        response_data: dict[str, Any] = {
            "id": f"chatcmpl-webui-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": use_model,
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
                "system_prompt_preview": system_preview,
            }
        
        # Store in buffer for dev console
        _REQUEST_BUFFER.append({
            "timestamp": datetime.now().isoformat(),
            "request": {
                "messages": messages,
                "model": model,
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
        
        # Get collection name from request, tester settings, or global settings
        collection_name = body.get("collection_name")
        if not collection_name and tester_settings:
            collection_name = tester_settings.get("rag_collection")
        if not collection_name or collection_name == "":
            collection_name = settings_repo.get_app_setting("rag_collection")
            if collection_name == "":
                collection_name = None
        
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
            # Rerank on/off from model settings (default off)
            use_rerank_tester = False
            try:
                proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
                if proxy_settings_json:
                    proxy_settings = json.loads(proxy_settings_json)
                    use_rerank_tester = bool(proxy_settings.get("rerank_for_rag", False))
            except Exception:
                pass
            effective_rerank_client = rerank_client if use_rerank_tester else None
            
            prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
            
            context_length = len(last_user.split())
            if not reasoning_level:
                reasoning_level = determine_reasoning_level(
                    last_user, context_length, ollama_model, None
                )
            
            top_k_override = top_k if top_k is not None else None
            ctx, rag_timings = build_rag_context(
                last_user,
                rag_repo,
                embed_provider,
                effective_rerank_client,
                params.context_chunk_chars,
                params.context_total_chars,
                top_k=top_k_override,
            )
            if rag_timings:
                set_latest_request_rag_steps(rag_timings)
            rag_chunks_info = ctx.chunks_info or None
            if rag_chunks_info:
                context_chars = sum(int(c.get("text_length") or 0) for c in rag_chunks_info)
            
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
    """Return the system prompt that will be used for Model Tester."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        prompt_name = body.get("prompt_name") or get_rag_prompt_name()
        swift_mode = body.get("swift_mode", "default")
        prefix, _ = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
        return jsonify({
            "prompt_name": prompt_name,
            "swift_mode": swift_mode,
            "system_prompt": prefix or "",
        })
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

                detailed.append(
                    {
                        "name": name,
                        "points_count": points_count,
                        "shards_count": shards_count,
                        "replication_factor": replication_factor,
                        "on_disk": on_disk,
                        "segments_count": segments_count,
                        "vectors_config": vectors_config,
                    }
                )
            except Exception as e:
                _WEBUI_LOG.warning("Failed to get collection %s via QdrantClient: %s", name, e)
                detailed.append({"name": name})

        return jsonify({"collections": detailed})
    except Exception as e:
        _WEBUI_LOG.error("Failed to get Qdrant collections: %s", e, exc_info=True)
        return jsonify({"collections": [], "error": str(e)}), 500


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


@webui_bp.route("/open-webui/status", methods=["GET"])
def open_webui_status() -> Any:
    """Return Open WebUI container status (reachable at OPEN_WEBUI_URL)."""
    url = _get_open_webui_url()
    status: dict[str, Any] = {"url": url, "running": False}
    try:
        resp = requests.get(url, timeout=3)
        status["http_status"] = resp.status_code
        if resp.ok:
            status["running"] = True
    except Exception as e:
        status["error"] = str(e)
        _WEBUI_LOG.debug("Open WebUI status check failed: %s", e)
    return jsonify(status)


@webui_bp.route("/open-webui/start", methods=["POST"])
def open_webui_start() -> Any:
    """Try to start Open WebUI Docker container."""
    name = _get_open_webui_container_name()
    ok, output = _run_docker_command(["start", name])
    status = 200 if ok else 500
    return jsonify({"ok": ok, "output": output, "container": name}), status


@webui_bp.route("/open-webui/stop", methods=["POST"])
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
            for field in ["language", "technology", "domain", "product", "doc_type"]:
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
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to create collection '{collection_name}': {e}")
        raise


def _create_collection_from_sources(
    collection_name: str,
    source_ids: list[str],
    chunk_max_size: int,
    chunk_min_size: int,
) -> dict[str, Any]:
    """
    Create a Qdrant collection by indexing pages from specified sources.
    Returns statistics about the indexing process.
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
    
    # Process each page
    for source_id, filename, entry, pages_dir, source_meta in candidates:
        page_path = os.path.join(pages_dir, filename)
        
        try:
            with open(page_path, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception as e:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Failed to read {source_id}/{filename}: {e}")
            continue
        
        # Simple validation - skip if too short
        if len(md.strip()) < 400:
            stats["skipped_pages"] += 1
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
            continue
        
        if not chunks_with_paths:
            stats["skipped_pages"] += 1
            continue
        
        chunk_texts = [t for t, _ in chunks_with_paths]
        
        # Get embeddings
        try:
            embeddings = _get_embeddings_simple(chunk_texts)
        except Exception as e:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Failed to get embeddings for {source_id}/{filename}: {e}")
            continue
        
        if not embeddings:
            stats["skipped_pages"] += 1
            continue
        
        dim = len(embeddings[0])
        if first_dim is None:
            first_dim = dim
            _ensure_collection_with_name(qclient, collection_name, first_dim)
        
        if dim != first_dim:
            stats["skipped_pages"] += 1
            stats["errors"].append(f"Dimension mismatch for {source_id}/{filename}: {dim} != {first_dim}")
            continue
        
        # Create points
        for (chunk_text, section_path), vec in zip(chunks_with_paths, embeddings):
            section_path_str = ":".join(section_path) if section_path else ""
            chunk_hash = _sha256(f"{source_id}:{filename}:{section_path_str}:{chunk_text}")
            point_id = _point_id_from_hash(chunk_hash)
            
            ios_versions, swift_versions = extract_versions(chunk_text)
            meta_extra = infer_metadata(
                source_id=source_id,
                filename=filename,
                url=entry.get("url"),
                section_path=section_path,
                text=chunk_text,
            )
            
            payload = {
                "source": source_id,
                "url": entry.get("url", ""),
                "path": f"pages/{filename}",
                "chunk_id": chunk_hash,
                "text": chunk_text,
                "section_path": section_path,
                "ios_versions": ios_versions,
                "swift_versions": swift_versions,
                "version": source_meta.get("last_crawled"),
                **meta_extra,
            }
            
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
        
        source_ids = _discover_sources()
        sources = []
        
        for source_id in source_ids:
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
            # Process finished, clean up
            del _crawling_processes[source_id]
            return jsonify({
                "status": "finished",
                "source_id": source_id,
                "return_code": return_code,
            })
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


@webui_bp.route("/crawler/create-collection", methods=["POST"])
def create_collection() -> Any:
    """Create a new Qdrant collection with specified configuration."""
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
        
        # Validate collection name format (Qdrant allows alphanumeric, underscore, hyphen)
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", collection_name):
            return jsonify({"error": "Collection name must contain only alphanumeric characters, underscores, and hyphens"}), 400
        
        # Check if collection already exists
        qdrant_url = get_qdrant_url().rstrip("/")
        qclient = QdrantClient(url=qdrant_url)
        try:
            qclient.get_collection(collection_name)
            return jsonify({"error": f"Collection '{collection_name}' already exists"}), 409
        except Exception:
            # Collection doesn't exist, which is what we want
            pass
        
        # Validate that sources have pages
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
        
        # Create collection
        try:
            stats = _create_collection_from_sources(
                collection_name=collection_name,
                source_ids=available_sources,
                chunk_max_size=chunk_max_size,
                chunk_min_size=chunk_min_size,
            )
            
            return jsonify({
                "status": "success",
                "collection_name": collection_name,
                "statistics": stats,
            })
        except Exception as e:
            _ERROR_LOG.error("webui_routes.create_collection indexing", exc_info=True)
            return jsonify({
                "error": f"Failed to create collection: {str(e)}",
                "collection_name": collection_name,
            }), 500
        
    except Exception as e:
        _ERROR_LOG.error("webui_routes.create_collection", exc_info=True)
        return jsonify({"error": str(e)}), 500


__all__ = ["webui_bp"]

