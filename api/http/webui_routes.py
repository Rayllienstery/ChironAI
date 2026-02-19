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
from subprocess import run
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
from config.rag_prompts import get_rag_system_prompt_swift_mode, list_rag_prompt_names
from domain.entities.rag import RagQuestionRequest
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.database import get_session_manager, get_logs_repository, get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from api.http.webui_session import log_to_database

import requests

# In-memory buffer for dev console (last 50 requests)
_REQUEST_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

webui_bp = Blueprint("webui", __name__, url_prefix="/api/webui")


@webui_bp.route("/models", methods=["GET"])
def get_models() -> Any:
    """Return list of available models from config."""
    try:
        model_name = get_ollama_chat_model()
        return jsonify({
            "models": [
                {"id": "rag-ollama", "name": "rag-ollama", "description": "RAG-enabled Ollama model"},
                {"id": model_name, "name": model_name, "description": f"Ollama chat model: {model_name}"},
            ]
        })
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
        since_id = request.args.get("since_id")
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id=session_id,
            level=level,
            limit=limit,
            since_id=int(since_id) if since_id else None,
        )
        
        return jsonify({"logs": logs})
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_logs", exc_info=True)
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
        model = body.get("model") or "rag-ollama"
        temperature = body.get("temperature")
        top_p = body.get("top_p")
        reasoning_level = body.get("reasoning_level")
        code_only = body.get("code_only", False)
        swift_mode = body.get("swift_mode", "default")
        prompt_name = body.get("prompt_name")
        include_rag_metadata = body.get("include_rag_metadata", True)
        
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        
        # Get RAG dependencies - try to find WebUI directory
        webui_dir = None
        possible_webui = os.path.join(_ROOT, "WebUI")
        if os.path.isdir(possible_webui):
            webui_dir = possible_webui
        params, deps = get_rag_answer_params(webui_dir=webui_dir)
        
        # Get prompt with Swift mode
        prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
        
        # Override params if prompt_name provided
        if prompt_name:
            params = params._replace(system_prefix=prefix, system_suffix=suffix)
        
        rag_repo = deps.rag_repo
        embed_provider = deps.embed_provider
        rerank_client = deps.rerank_client
        chat_client = deps.chat_client
        
        last_user = last_user_content(messages)
        context_length = len(last_user.split())
        ollama_model = params.model_name
        
        # Determine reasoning level
        if not reasoning_level:
            reasoning_level = determine_reasoning_level(
                last_user, context_length, ollama_model, None
            )
        
        # Build RAG context to get chunks_info
        ctx = build_rag_context(
            last_user,
            rag_repo,
            embed_provider,
            rerank_client,
            params.context_chunk_chars,
            params.context_total_chars,
        )
        
        # Prepare messages
        req = RagQuestionRequest(
            messages=messages,
            model=model,
            stream=False,
            reasoning_level=reasoning_level,
        )
        
        ollama_messages, use_model = prepare_ollama_messages(
            req,
            rag_repo,
            embed_provider,
            rerank_client,
            prefix,
            suffix,
            params.context_chunk_chars,
            params.context_total_chars,
            params.confidence_threshold,
            ollama_model,
            reasoning_level=reasoning_level,
        )
        
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
        content = chat_client.chat(ollama_messages, use_model, stream=False, options=options if options else None)
        
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
        return jsonify({
            "model": get_ollama_chat_model(),
            "prompt_name": get_rag_prompt_name(),
            "swift_mode": "default",
            "temperature": get_rag_float("temperature", 0.0),
            "top_p": get_rag_float("top_p", 0.1),
            "reasoning_level": "",
            "code_only": False,
            "include_rag_metadata": True,
        })
    except Exception as e:
        _ERROR_LOG.error("webui_routes.get_model_settings", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/model-settings", methods=["POST"])
def update_model_settings() -> Any:
    """Update model settings (stored in memory/session, not persisted to config)."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        # For now, just return success - settings are per-request in chat endpoint
        # In future, could store in database per session
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
                "prompt_name": get_rag_prompt_name(),
                "swift_mode": "default",
                "temperature": 0.0,
                "top_p": 0.1,
                "reasoning_level": "",
                "use_rag": True,
            })
        
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
        prompt_name = body.get("prompt_name")
        swift_mode = body.get("swift_mode", "default")
        temperature = body.get("temperature")
        top_p = body.get("top_p")
        reasoning_level = body.get("reasoning_level")
        
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        # Get tester settings if not provided
        if not prompt_name or not swift_mode:
            settings_repo = get_settings_repository()
            tester_settings = settings_repo.get_tester_settings(session_id)
            if tester_settings:
                prompt_name = prompt_name or tester_settings.get("prompt_name")
                swift_mode = swift_mode or tester_settings.get("swift_mode", "default")
                temperature = temperature if temperature is not None else tester_settings.get("temperature")
                top_p = top_p if top_p is not None else tester_settings.get("top_p")
                reasoning_level = reasoning_level or tester_settings.get("reasoning_level")
                use_rag = use_rag if "use_rag" in body else tester_settings.get("use_rag", True)
        
        # Defaults from config
        prompt_name = prompt_name or get_rag_prompt_name()
        
        params, deps = get_rag_answer_params()
        chat_client = deps.chat_client
        ollama_model = params.model_name
        
        last_user = last_user_content(messages)
        
        if use_rag:
            # Use RAG flow
            rag_repo = deps.rag_repo
            embed_provider = deps.embed_provider
            rerank_client = deps.rerank_client
            
            prefix, suffix = get_rag_system_prompt_swift_mode(prompt_name, swift_mode)
            
            context_length = len(last_user.split())
            if not reasoning_level:
                reasoning_level = determine_reasoning_level(
                    last_user, context_length, ollama_model, None
                )
            
            ctx = build_rag_context(
                last_user,
                rag_repo,
                embed_provider,
                rerank_client,
                params.context_chunk_chars,
                params.context_total_chars,
            )
            
            req = RagQuestionRequest(
                messages=messages,
                model="rag-ollama",
                stream=False,
                reasoning_level=reasoning_level,
            )
            
            ollama_messages, use_model = prepare_ollama_messages(
                req,
                rag_repo,
                embed_provider,
                rerank_client,
                prefix,
                suffix,
                params.context_chunk_chars,
                params.context_total_chars,
                params.confidence_threshold,
                ollama_model,
                reasoning_level=reasoning_level,
            )
        else:
            # Direct chat without RAG
            use_model = ollama_model
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
        content = chat_client.chat(ollama_messages, use_model, stream=False, options=options if options else None)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Build response
        response_data: dict[str, Any] = {
            "id": f"chatcmpl-tester-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": use_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content or ""},
                "finish_reason": "stop",
            }],
        }
        
        return jsonify(response_data)
    except Exception as e:
        _ERROR_LOG.error("webui_routes.tester_chat", exc_info=True)
        return jsonify({"error": str(e)}), 500


@webui_bp.route("/settings", methods=["GET"])
def get_settings() -> Any:
    """Get app settings."""
    try:
        settings_repo = get_settings_repository()
        settings = settings_repo.get_all_app_settings()
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
  return jsonify(status)


@webui_bp.route("/rag/collections", methods=["GET"])
def rag_collections() -> Any:
    """Return detailed information about Qdrant collections."""
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=5)
        if not resp.ok:
            return jsonify({"collections": [], "error": f"HTTP {resp.status_code}"}), resp.status_code
        data = resp.json() or {}
        collections = data.get("result", {}).get("collections", [])

        detailed: list[dict[str, Any]] = []
        for col in collections:
            name = col.get("name")
            if not name:
                continue
            try:
                c_resp = requests.get(f"{url}/collections/{name}", timeout=5)
                if not c_resp.ok:
                    detailed.append({"name": name})
                    continue
                c_data = c_resp.json() or {}
                result = c_data.get("result", {})
                config = result.get("config", {})
                status = result.get("status", {})
                detailed.append(
                    {
                        "name": name,
                        "points_count": status.get("points_count"),
                        "shards_count": config.get("shard_number"),
                        "replication_factor": config.get("replication_factor"),
                        "on_disk": bool(config.get("on_disk_payload")),
                    }
                )
            except Exception:
                detailed.append({"name": name})
        return jsonify({"collections": detailed})
    except Exception as e:
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


__all__ = ["webui_bp"]

