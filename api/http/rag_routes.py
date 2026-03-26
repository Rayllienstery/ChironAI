"""
Flask routes for OpenAI-compatible RAG proxy.

Exposes /v1/models, /v1/chat/completions, /, /v1, /health.
Uses application.rag.use_cases with wired dependencies from application.container.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
import uuid

from flask import Flask, Response, jsonify, request

# Ensure project root on path when running from api or WebUI.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# So that "from rag_service ..." works (rag_service package lives in modules/rag_service).
_MODULES_RAG = os.path.join(_ROOT, "modules", "rag_service")
if _MODULES_RAG not in sys.path:
    sys.path.insert(0, _MODULES_RAG)
# External docs RAG module (multi-collection, trigger keywords).
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)

from application.rag.collection_freshness import check_collection_freshness
from application.rag.params import RAGDependencies, get_rag_answer_params
from application.rag.use_cases import build_rag_context, prepare_ollama_messages
from domain.entities.rag import RagQuestionRequest
from infrastructure.database import get_settings_repository

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
    load_rag_sources_config = None  # type: ignore[assignment]
    load_external_sources = None  # type: ignore[assignment]
    load_github_repos = None  # type: ignore[assignment]
    ingest_github_repo_markdown = None  # type: ignore[assignment]
    HttpFetchClient = None  # type: ignore[assignment]
    QdrantChunkSink = None  # type: ignore[assignment]
    QdrantRagSearchAdapter = None  # type: ignore[assignment]
    get_latest_release_tag = None  # type: ignore[assignment]
    _EXTERNAL_DOCS_RAG_AVAILABLE = False

try:
    from config import (
        get_default_rag_top_k,
        get_framework_collection_ttl_days,
        get_proxy_rerank_enabled,
        get_qdrant_url,
    )
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment]
    get_default_rag_top_k = lambda: 4  # type: ignore[assignment]
try:
    from rag_service.infrastructure.keyword_collections_sqlite import get_keyword_collections_repository
except ImportError:
    get_keyword_collections_repository = None  # type: ignore[assignment]


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
from domain.services.prompt_builder import determine_reasoning_level, last_user_content
from infrastructure.logging.webui_error_logger import log_webui_error
from infrastructure.database import get_session_manager, get_logs_repository
from api.http.proxy_status import (
    set_proxy_status,
    set_latest_request_seconds,
    set_latest_request_total_tokens,
    set_latest_request_rag_steps,
    STATUS_IDLE,
    STATUS_RAG_SEARCH,
    STATUS_PREPARING_RESPONSE,
    STATUS_RESPONSE,
)
from api.http.proxy_trace import set_current_trace
import time

RAG_MODEL_ID = "rag-ollama"
_RAG_LOG = logging.getLogger("trag.rag")
_APPLY_EDIT_TOOL_NAME = "apply_file_edit"


def _log_rag_error(stage: str, error: Exception) -> None:
    """One-line console log: RAG stage=... | ErrorType: message."""
    _RAG_LOG.error("RAG stage=%s | %s: %s", stage, type(error).__name__, error)


def _workspace_root() -> Path:
    return Path(_ROOT).resolve()


def _resolve_workspace_path(file_path: str) -> Path:
    if not file_path or not str(file_path).strip():
        raise ValueError("file_path is required")
    root = _workspace_root()
    candidate = Path(file_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("file_path points outside workspace") from exc
    return resolved


def _replace_text_range(original: str, range_data: dict[str, object], new_text: str) -> str:
    lines = original.splitlines(keepends=True)
    start_line = int(range_data.get("start_line") or 0)
    end_line = int(range_data.get("end_line") or 0)
    start_col = int(range_data.get("start_col") or 1)
    end_col = int(range_data.get("end_col") or 1)
    if start_line < 1 or end_line < 1 or start_line > end_line:
        raise ValueError("Invalid range: line indices")
    if start_line > len(lines) or end_line > len(lines):
        raise ValueError("Range out of bounds")
    start_line_text = lines[start_line - 1]
    end_line_text = lines[end_line - 1]
    if start_col < 1 or start_col > (len(start_line_text) + 1):
        raise ValueError("Invalid range: start_col")
    if end_col < 1 or end_col > (len(end_line_text) + 1):
        raise ValueError("Invalid range: end_col")
    if start_line == end_line and end_col < start_col:
        raise ValueError("Invalid range: end_col before start_col")

    prefix = "".join(lines[: start_line - 1]) + start_line_text[: start_col - 1]
    suffix = end_line_text[end_col - 1 :] + "".join(lines[end_line:])
    return f"{prefix}{new_text}{suffix}"


def _extract_edit_from_response(content: str) -> dict[str, object] | None:
    text = (content or "").strip()
    if not text:
        return None
    # Accept plain JSON or fenced JSON block.
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    payload = m.group(1) if m else text
    try:
        obj = json.loads(payload)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    file_path = obj.get("file_path") or obj.get("path")
    if not file_path:
        return None
    if not (obj.get("new_text") or obj.get("patch") or obj.get("replacement") or obj.get("content")):
        return None
    if "file_path" not in obj:
        obj["file_path"] = file_path
    if "new_text" not in obj:
        obj["new_text"] = obj.get("replacement") or obj.get("content") or ""
    return obj


def _normalize_tool_path(file_path: str) -> str:
    raw = (file_path or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    if normalized.startswith("file:///"):
        normalized = normalized[8:]
    root = _workspace_root()
    try:
        candidate = Path(normalized)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            try:
                rel = resolved.relative_to(root)
                return rel.as_posix()
            except ValueError:
                return normalized
    except Exception:
        return normalized
    return normalized.lstrip("./")


def _extract_tool_name(tool_obj: object) -> str | None:
    if not isinstance(tool_obj, dict):
        return None
    fn = tool_obj.get("function")
    if not isinstance(fn, dict):
        return None
    name = fn.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _select_edit_tool_name(tools: list[object]) -> str | None:
    names = [n for n in (_extract_tool_name(t) for t in tools) if n]
    if not names:
        return None
    if _APPLY_EDIT_TOOL_NAME in names:
        return _APPLY_EDIT_TOOL_NAME
    for n in names:
        low = n.lower()
        if "file" in low and ("edit" in low or "patch" in low or "replace" in low or "range" in low):
            return n
    for n in names:
        low = n.lower()
        if "edit" in low or "patch" in low or "replace" in low:
            return n
    # Tool `save_file` is a valid file operation even though it doesn't contain
    # substrings like `edit`/`patch`/`replace`.
    for n in names:
        low = n.lower()
        if low == "save_file" or "save_file" in low:
            return n
    return None


def _get_tool_by_name(tools: list[object], name: str | None) -> dict[str, object] | None:
    if not name:
        return None
    for t in tools:
        if not isinstance(t, dict):
            continue
        if _extract_tool_name(t) == name:
            return t
    return None


def _build_tool_arguments(
    *,
    selected_tool_name: str,
    selected_tool: dict[str, object] | None,
    edit_payload: dict[str, object],
    user_query: str,
) -> dict[str, object]:
    file_path = _normalize_tool_path(str(edit_payload.get("file_path") or ""))
    range_obj = edit_payload.get("range") if isinstance(edit_payload.get("range"), dict) else {}
    new_text = str(edit_payload.get("new_text") or "")
    desc = (user_query or "").strip().replace("\n", " ")
    if not desc:
        desc = f"Apply requested edit via {selected_tool_name}"
    display_description = desc[:180]

    payload_mode = edit_payload.get("mode")
    mode_value = (
        payload_mode.strip()
        if isinstance(payload_mode, str) and payload_mode.strip()
        else "edit"
    )

    canonical_values: dict[str, object] = {
        "file_path": file_path,
        "path": file_path,
        "target_file": file_path,
        "new_text": new_text,
        "replacement": new_text,
        "text": new_text,
        "content": new_text,
        "new_content": new_text,
        "range": range_obj,
        "line_range": range_obj,
        "location": range_obj,
        "start_line": range_obj.get("start_line"),
        "end_line": range_obj.get("end_line"),
        "start_col": range_obj.get("start_col"),
        "end_col": range_obj.get("end_col"),
        "display_description": display_description,
        "mode": mode_value,
        "operation": "edit",
        "variant": "edit",
    }

    # If tool schema provides required keys, ensure they are present to avoid Zed-side rejection.
    properties: dict[str, object] = {}
    required: list[str] = []
    try:
        fn = selected_tool.get("function") if isinstance(selected_tool, dict) else None
        params = fn.get("parameters") if isinstance(fn, dict) else None
        if isinstance(params, dict) and isinstance(params.get("properties"), dict):
            properties = params.get("properties")  # type: ignore[assignment]
        if isinstance(params, dict) and isinstance(params.get("required"), list):
            required = [str(x) for x in params.get("required") if isinstance(x, str)]
    except Exception:
        required = []

    # Strict native mode: only schema keys (+ required keys) are emitted.
    keys_to_emit: set[str] = set(required)
    keys_to_emit.update(str(k) for k in properties.keys())
    if not keys_to_emit:
        keys_to_emit = {"file_path", "range", "new_text"}

    # Special handling for save-file batch payload (`paths`).
    # Some clients require tool input like:
    #   paths=[{"path": "...", "content": "..."}]
    # rather than a single `path`.
    if "paths" in keys_to_emit:
        payload_paths = edit_payload.get("paths")
        if isinstance(payload_paths, list):
            normalized_paths: list[dict[str, object]] = []
            for p in payload_paths:
                if isinstance(p, dict):
                    p_path_raw = p.get("path") or p.get("file_path") or ""
                    p_content_raw = (
                        p.get("content")
                        or p.get("new_text")
                        or p.get("text")
                        or new_text
                    )
                    p_path = _normalize_tool_path(str(p_path_raw)) if p_path_raw else ""
                    p_content = str(p_content_raw) if p_content_raw is not None else ""
                    normalized_paths.append({"path": p_path, "content": p_content})
                elif isinstance(p, str):
                    normalized_paths.append(
                        {"path": _normalize_tool_path(p) if p else "", "content": new_text}
                    )
            canonical_values["paths"] = normalized_paths
        elif file_path:
            canonical_values["paths"] = [{"path": file_path, "content": new_text}]

    args: dict[str, object] = {}
    for key in keys_to_emit:
        if key in canonical_values and canonical_values[key] not in (None, ""):
            args[key] = canonical_values[key]
        elif key in edit_payload:
            # Passthrough: preserve client/model-provided fields that aren't derived
            # by canonical_values (helps with schema variations).
            val = edit_payload.get(key)
            if val not in (None, ""):
                if key in ("path", "file_path", "target_file") and not isinstance(val, str):
                    args[key] = str(val)
                else:
                    args[key] = val

    # Guarantee required fields are present, with conservative defaults.
    for key in required:
        if key in args and args.get(key) not in (None, ""):
            continue
        if key in canonical_values:
            args[key] = canonical_values[key]
        elif key in edit_payload and edit_payload.get(key) not in (None, ""):
            args[key] = edit_payload.get(key)  # type: ignore[assignment]
        elif key == "display_description":
            args[key] = display_description
        else:
            args[key] = [] if key == "paths" else ""

    return args


def _build_tool_json_instruction(
    selected_tool_name: str | None,
    selected_tool: dict[str, object] | None,
) -> str:
    if not selected_tool_name or not isinstance(selected_tool, dict):
        return ""
    fn = selected_tool.get("function") if isinstance(selected_tool.get("function"), dict) else {}
    params = fn.get("parameters") if isinstance(fn, dict) else {}
    required = params.get("required") if isinstance(params, dict) and isinstance(params.get("required"), list) else []
    properties = params.get("properties") if isinstance(params, dict) and isinstance(params.get("properties"), dict) else {}
    prop_names = [str(k) for k in properties.keys()]
    req_names = [str(x) for x in required if isinstance(x, str)]
    fields = req_names if req_names else prop_names
    if not fields:
        fields = ["path", "range", "new_text"]
    return (
        "Tool-call mode is enabled. "
        f"Return ONLY a single valid JSON object for tool `{selected_tool_name}` with fields from tool schema: {fields}. "
        "Do not return markdown, code fences, comments, or explanations. "
        "Use workspace-relative path in `path`/`file_path` when applicable. "
        "If any field is unknown, use an empty string."
    )


def create_app(
    webui_dir: str | None = None,
    system_prefix: str | None = None,
    system_suffix: str | None = None,
) -> Flask:
    """
    Create Flask app with RAG routes.
    webui_dir: directory containing last_collection.txt (e.g. WebUI).
    system_prefix/suffix: optional overrides for RAG system prompt; if None use config (same as rag_client).
    """
    app = Flask(__name__)
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    prefix = system_prefix if system_prefix is not None else params.system_prefix
    suffix = system_suffix if system_suffix is not None else params.system_suffix
    context_chunk_chars = params.context_chunk_chars
    context_total_chars = params.context_total_chars
    confidence_threshold = params.confidence_threshold
    ollama_model = params.model_name
    log_preview = params.log_preview_chars
    rag_repo = deps.rag_repo
    embed_provider = deps.embed_provider
    rerank_client = deps.rerank_client
    chat_client = deps.chat_client

    @app.route("/")
    def index() -> Response:
        """Redirect root to WebUI."""
        return Response(
            '<!DOCTYPE html><html><head><meta http-equiv="refresh" '
            'content="0; url=/webui"></head><body>'
            '<p>Redirecting to <a href="/webui">/webui</a>...</p>'
            "</body></html>",
            status=302,
            headers={"Location": "/webui"},
            mimetype="text/html; charset=utf-8",
        )

    @app.route("/v1", methods=["GET"])
    def v1_root() -> Response:
        return jsonify({"object": "api", "version": "v1"})

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.route("/v1/models", methods=["GET"])
    def list_models() -> Response:
        return jsonify({
            "object": "list",
            "data": [{"id": RAG_MODEL_ID, "object": "model", "created": 0, "owned_by": "local"}],
        })

    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions() -> Response | tuple[Response, int]:
        start_time = time.time()
        user_query = ""
        rag_context_data = None
        response_content = ""
        latency_ms = 0
        prompt_tokens_approx = 0
        completion_tokens_approx = 0
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        trace = {
            "trace_id": trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request": {},
            "internet": {},
            "rag": {},
            "ollama": {},
            "response": {},
            "steps": [],
        }
        set_current_trace(trace)
        
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "parse_body"})
            _log_rag_error("parse_body", e)
            return jsonify({"error": "Invalid JSON"}), 400
        messages = body.get("messages") or []
        stream = body.get("stream", False)
        requested_model = body.get("model") or RAG_MODEL_ID
        tools = body.get("tools") if isinstance(body.get("tools"), list) else []
        tool_choice = body.get("tool_choice")
        selected_edit_tool_name = _select_edit_tool_name(tools)
        selected_edit_tool = _get_tool_by_name(tools, selected_edit_tool_name) if selected_edit_tool_name else None
        explicit_reasoning = body.get("reasoning_level") or body.get("reasoning")
        include_rag_metadata = body.get("include_rag_metadata", False)
        force_rag = bool(body.get("force_rag"))
        has_tool_result = any(isinstance(m, dict) and m.get("role") == "tool" for m in messages)
        fetch_web_knowledge_raw = body.get("fetch_web_knowledge")
        if fetch_web_knowledge_raw is None:
            fetch_web_knowledge = False
            try:
                settings_repo = get_settings_repository()
                proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
                if proxy_settings_json:
                    proxy_settings = json.loads(proxy_settings_json)
                    fetch_web_knowledge = bool(proxy_settings.get("fetch_web_knowledge", False))
            except Exception:
                fetch_web_knowledge = False
        else:
            fetch_web_knowledge = bool(fetch_web_knowledge_raw)
        if not messages:
            return jsonify({"error": "messages is required"}), 400
        set_proxy_status(STATUS_RAG_SEARCH)
        last_user = last_user_content(messages)
        user_query = last_user  # Store for logging
        context_length = len(last_user.split())
        effective_prefix = prefix
        effective_suffix = suffix
        effective_context_chunk_chars = context_chunk_chars
        effective_context_total_chars = context_total_chars
        effective_confidence_threshold = confidence_threshold
        effective_rag_repo = rag_repo
        effective_embed_provider = embed_provider
        effective_base_rerank_client = rerank_client
        effective_ollama_model = ollama_model
        reasoning_level = determine_reasoning_level(
            last_user, context_length, effective_ollama_model, explicit_reasoning
        )
        
        # If model is "rag-ollama", use config model instead (rag-ollama is just a proxy identifier)
        actual_model = (
            effective_ollama_model
            if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID
            else requested_model
        )

        trace["request"] = {
            "requested_model": requested_model,
            "actual_model": actual_model,
            "stream": bool(stream),
            "include_rag_metadata": bool(include_rag_metadata),
            "tools_count": len(tools),
            "tools_names_preview": [n for n in (_extract_tool_name(t) for t in tools) if n][:20],
            "selected_edit_tool_name": selected_edit_tool_name,
            "selected_edit_tool_required": (
                (
                    ((selected_edit_tool or {}).get("function") or {}).get("parameters") or {}
                ).get("required")
                if isinstance(selected_edit_tool, dict)
                else None
            ),
            "tool_choice": tool_choice if isinstance(tool_choice, (str, dict)) else None,
            "has_tool_result": bool(has_tool_result),
            "force_rag": bool(force_rag),
            "fetch_web_knowledge": bool(fetch_web_knowledge),
            "reasoning_level": explicit_reasoning or reasoning_level,
            "user_query_preview": (user_query or "")[:500],
        }

        # Optional project_context: frameworks list -> fresh collection names for RAG filter, and needs_refresh for background index
        project_context = body.get("project_context")
        project_fresh_collection_names: set[str] | None = None
        needs_refresh: list[tuple[str, str]] = []  # (framework_id_lower, collection_name); also filled from resolved sources below
        if (
            fetch_web_knowledge
            and isinstance(project_context, dict)
            and _EXTERNAL_DOCS_RAG_AVAILABLE
            and load_rag_sources_config
        ):
            frameworks = project_context.get("frameworks") or []
            if frameworks:
                rag_sources_config = load_rag_sources_config()
                # Map framework name (e.g. "Alamofire") -> collection_name from config
                name_to_collection: dict[str, str] = {}
                for cfg in rag_sources_config:
                    for kw in (cfg.trigger_keywords or []):
                        name_to_collection[(kw or "").strip().lower()] = cfg.collection_name
                    if (cfg.external_source_id or "").strip():
                        name_to_collection[(cfg.external_source_id or "").strip().lower()] = cfg.collection_name
                ttl_days = get_framework_collection_ttl_days()
                settings_repo = None
                try:
                    settings_repo = get_settings_repository()
                    ttl_raw = settings_repo.get_app_setting("framework_collection_ttl_days")
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
                    if settings_repo:
                        try:
                            meta = settings_repo.get_collection_meta(coll)
                        except Exception:
                            pass
                    if check_collection_freshness(meta, ttl_days) == "fresh":
                        if coll not in fresh_collections:
                            fresh_collections.append(coll)
                    else:
                        needs_refresh.append((name.lower(), coll))
                project_fresh_collection_names = set(fresh_collections) if fresh_collections else None

        # Resolve collection in priority order:
        # 1) request body collection_name
        # 2) app_settings.rag_collection
        # 3) proxy_settings.rag_collection (backward-compatible / single blob settings)
        # 4) default wiring (collection file/config) when none are set
        request_collection = (body.get("collection_name") or "").strip() or None
        collection_source = "request"
        if not request_collection:
            try:
                settings_repo = get_settings_repository()
                request_collection = (settings_repo.get_app_setting("rag_collection") or "").strip() or None
                collection_source = "app_settings.rag_collection"
                if not request_collection:
                    proxy_settings_json = settings_repo.get_app_setting("proxy_settings")
                    if proxy_settings_json:
                        proxy_settings = json.loads(proxy_settings_json)
                        request_collection = (proxy_settings.get("rag_collection") or "").strip() or None
                        if request_collection:
                            collection_source = "proxy_settings.rag_collection"
            except Exception:
                request_collection = None
                collection_source = "default"
        if request_collection:
            req_params, req_deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=request_collection)
            effective_prefix = system_prefix if system_prefix is not None else req_params.system_prefix
            effective_suffix = system_suffix if system_suffix is not None else req_params.system_suffix
            effective_context_chunk_chars = req_params.context_chunk_chars
            effective_context_total_chars = req_params.context_total_chars
            effective_confidence_threshold = req_params.confidence_threshold
            effective_ollama_model = req_params.model_name
            effective_rag_repo = req_deps.rag_repo
            effective_embed_provider = req_deps.embed_provider
            effective_base_rerank_client = req_deps.rerank_client
            actual_model = (
                effective_ollama_model
                if requested_model == "rag-ollama" or requested_model == RAG_MODEL_ID
                else requested_model
            )
            trace["request"]["actual_model"] = actual_model
            trace["request"]["collection_name"] = request_collection
            trace["request"]["collection_source"] = collection_source
        else:
            trace["request"]["collection_source"] = "default"

        # Proxy: do not read settings from DB; rerank is configurable via proxy_rerank_enabled.
        effective_rerank_client = (
            effective_base_rerank_client if get_proxy_rerank_enabled() else None
        )
        rag_keywords = _get_rag_required_keywords_from_module()

        # Build RAG context: multi-collection (external_docs_rag) when triggered, else single collection
        rag_ctx_for_log = None
        rag_timings: dict[str, float] = {"embed_s": 0.0, "search_s": 0.0, "rerank_s": 0.0, "total_rag_s": 0.0}
        background_refresh_started = False
        trace["internet"] = {"background_refresh_started": False}
        try:
            use_merged = False
            if (
                fetch_web_knowledge
                and not request_collection
                and _EXTERNAL_DOCS_RAG_AVAILABLE
                and load_rag_sources_config
                and resolve_rag_sources_for_request
                and build_merged_rag_context
                and QdrantRagSearchAdapter is not None
            ):
                rag_sources_config = load_rag_sources_config()
                body_rag_sources = body.get("rag_sources")
                if isinstance(body_rag_sources, list):
                    body_rag_sources = [str(x) for x in body_rag_sources]
                else:
                    body_rag_sources = None
                resolved = resolve_rag_sources_for_request(last_user, messages, body_rag_sources, rag_sources_config)
                # Use merged path whenever we have any resolved source: enables generic discovery
                # (GitHub fetch for any framework name in the question) plus configured on-demand and RAG.
                if len(resolved) >= 1:
                    use_merged = True
                    # Trigger full crawl for resolved sources that are missing or stale when repo is on GitHub
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
                                        fetch_client, chunk_sink, effective_embed_provider,
                                        max_depth=3,
                                        on_indexed=on_indexed,
                                    )
                                    break
                            except Exception as e:
                                _RAG_LOG.warning("Background framework refresh failed: %s", e)

                        background_refresh_started = True
                        trace["internet"]["background_refresh_started"] = True
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
                        effective_embed_provider,
                        effective_context_chunk_chars,
                        effective_context_total_chars,
                        fetch_client=fetch_client,
                        external_sources=external_sources_list,
                        fresh_collection_names=project_fresh_collection_names,
                    )
                    from domain.entities.rag import RagContext
                    rag_ctx_for_log = RagContext(
                        context_text=merged_ctx.context_text,
                        chunks_info=merged_ctx.chunks_info,
                        max_score=merged_ctx.max_score,
                    )
                    rag_timings = merged_timings
            if not use_merged or rag_ctx_for_log is None:
                rag_ctx_for_log, rag_timings = build_rag_context(
                    last_user,
                    effective_rag_repo,
                    effective_embed_provider,
                    effective_rerank_client,
                    effective_context_chunk_chars,
                    effective_context_total_chars,
                    rag_required_keywords=rag_keywords,
                    trigger_threshold=None,
                    force_rag=force_rag,
                )
            if rag_timings:
                set_latest_request_rag_steps(rag_timings)
                _RAG_LOG.info(
                    "RAG steps embed_s=%.2f search_s=%.2f rerank_s=%.2f fetch_s=%.2f discovery_s=%.2f total_rag_s=%.2f",
                    rag_timings.get("embed_s", 0),
                    rag_timings.get("search_s", 0),
                    rag_timings.get("rerank_s", 0),
                    rag_timings.get("fetch_s", 0),
                    rag_timings.get("discovery_s", 0),
                    rag_timings.get("total_rag_s", 0),
                )
            if rag_ctx_for_log:
                rag_context_data = {
                    "chunks_count": len(rag_ctx_for_log.chunks_info),
                    "max_score": rag_ctx_for_log.max_score,
                    "context_length": len(rag_ctx_for_log.context_text),
                    "chunks_info": rag_ctx_for_log.chunks_info[:5] if rag_ctx_for_log.chunks_info else [],
                }
            else:
                rag_context_data = None
            
            # Enrich trace for the UI
            trace["rag"]["timings"] = dict(rag_timings or {})
            trace["internet"].update(
                {
                    "fetch_s": float((rag_timings or {}).get("fetch_s", 0.0) or 0.0),
                    "discovery_s": float((rag_timings or {}).get("discovery_s", 0.0) or 0.0),
                }
            )
            trace["internet"]["used"] = bool(
                (rag_timings or {}).get("fetch_s")
                or (rag_timings or {}).get("discovery_s")
                or background_refresh_started
            )
            if rag_ctx_for_log:
                trace["rag"]["context"] = {
                    "context_chars_used": len(rag_ctx_for_log.context_text or ""),
                    "context_budget_chars": int(effective_context_total_chars or 0),
                    "context_text_preview": (rag_ctx_for_log.context_text or "")[:2000],
                    "chunks": rag_ctx_for_log.chunks_info[:20] if rag_ctx_for_log.chunks_info else [],
                }
                trace["rag"]["tokens_estimates"] = {
                    "embed_tokens_in": rag_timings.get("embed_tokens_in"),
                    "rerank_prompt_tokens_in": rag_timings.get("rerank_prompt_tokens_in"),
                    "fetch_tokens_in": rag_timings.get("fetch_tokens_in"),
                    "discovery_tokens_in": rag_timings.get("discovery_tokens_in"),
                }
            else:
                trace["rag"]["context"] = None

            # RAG sub-steps (timeline for the UI)
            _rt = rag_timings or {}
            _steps: list[dict[str, object]] = []

            def _add_step(name: str, dur_s: float, tokens_in_est: object | None = None) -> None:
                if dur_s and dur_s > 0:
                    _steps.append(
                        {
                            "name": name,
                            "duration_ms": int(dur_s * 1000),
                            "tokens_in_est": tokens_in_est,
                            "tokens_out_est": 0,
                        }
                    )

            _add_step("embed", float(_rt.get("embed_s", 0.0) or 0.0), _rt.get("embed_tokens_in"))
            _add_step("search", float(_rt.get("search_s", 0.0) or 0.0), None)
            _add_step("rerank", float(_rt.get("rerank_s", 0.0) or 0.0), _rt.get("rerank_prompt_tokens_in"))
            _add_step("fetch", float(_rt.get("fetch_s", 0.0) or 0.0), _rt.get("fetch_tokens_in"))
            _add_step("discovery", float(_rt.get("discovery_s", 0.0) or 0.0), _rt.get("discovery_tokens_in"))
            _add_step("total_rag", float(_rt.get("total_rag_s", 0.0) or 0.0), None)
            trace["steps"] = _steps
            set_current_trace(trace)
        except Exception as e:
            _RAG_LOG.warning(f"Failed to build RAG context for logging: {e}")
            rag_context_data = None
        set_proxy_status(STATUS_PREPARING_RESPONSE)
        
        # Reuse the same RAG context for messages (single RAG call per request)
        rag_ctx = rag_ctx_for_log if (include_rag_metadata and rag_ctx_for_log) else None
        try:
            req = RagQuestionRequest(
                messages=messages,
                model=actual_model,  # Use actual_model instead of requested_model
                stream=stream,
                reasoning_level=reasoning_level,
            )
            ollama_messages, use_model = prepare_ollama_messages(
                req,
                effective_rag_repo,
                effective_embed_provider,
                effective_rerank_client,
                effective_prefix,
                effective_suffix,
                effective_context_chunk_chars,
                effective_context_total_chars,
                effective_confidence_threshold,
                effective_ollama_model,
                reasoning_level=reasoning_level,
                rag_required_keywords=rag_keywords,
                rag_context=rag_ctx_for_log,
                trigger_threshold=None,
                force_rag=force_rag,
            )
            # Ensure use_model is not "rag-ollama" - use config model if needed
            if use_model == "rag-ollama":
                use_model = effective_ollama_model

            # Store what we send to Ollama (preview + sizes only)
            _msg_preview_limit = 300
            _ollama_messages_preview: list[dict[str, object]] = []
            for m in ollama_messages:
                if not isinstance(m, dict):
                    continue
                role = m.get("role") or ""
                content_str = m.get("content") or ""
                content_len = len(content_str)
                _ollama_messages_preview.append(
                    {
                        "role": str(role),
                        "content_length_chars": int(content_len),
                        "content_preview": content_str[:_msg_preview_limit]
                        + ("..." if content_len > _msg_preview_limit else ""),
                    }
                )
            trace["ollama"]["model"] = use_model
            trace["ollama"]["messages"] = _ollama_messages_preview
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "prepare_rag"})
            _log_rag_error("prepare_rag", e)
            return jsonify({"error": str(e)}), 500

        if tools and tool_choice != "none" and not has_tool_result:
            tool_json_instruction = _build_tool_json_instruction(selected_edit_tool_name, selected_edit_tool)
            if tool_json_instruction:
                ollama_messages.append({"role": "system", "content": tool_json_instruction})

        stream_tool_mode = bool(stream and tools and tool_choice != "none" and not has_tool_result)
        if stream_tool_mode:
            set_proxy_status(STATUS_RESPONSE)
            stream_start_time = time.time()
            stream_tool_error: str | None = None
            try:
                streamed_content = chat_client.chat(ollama_messages, use_model, stream=False, options=None)
            except Exception as e:
                # Retry once with compact context; large prompts can trigger Ollama 500 on some models.
                compact_messages: list[dict[str, object]] = []
                if ollama_messages:
                    first_system = next((m for m in ollama_messages if isinstance(m, dict) and m.get("role") == "system"), None)
                    last_user_msg = next((m for m in reversed(ollama_messages) if isinstance(m, dict) and m.get("role") == "user"), None)
                    if isinstance(first_system, dict):
                        compact_messages.append(first_system)
                    if isinstance(last_user_msg, dict):
                        compact_messages.append(last_user_msg)
                try:
                    streamed_content = chat_client.chat(compact_messages or ollama_messages, use_model, stream=False, options=None)
                except Exception as e2:
                    log_webui_error("rag_routes.chat_completions", e2, {"stage": "chat_stream_tool_mode"})
                    _log_rag_error("chat_stream_tool_mode", e2)
                    stream_tool_error = str(e2)
                    streamed_content = ""
            finally:
                set_proxy_status(STATUS_IDLE)
                set_latest_request_seconds(time.time() - start_time)

            if stream_tool_error:
                # Do not fail the whole request: fallback to plain streaming branch below.
                trace["response"]["tool_mode_error"] = stream_tool_error[:500]
                set_current_trace(trace)
            edit_payload = _extract_edit_from_response(streamed_content or "")

            if (not stream_tool_error) and edit_payload and selected_edit_tool_name and selected_edit_tool:
                tool_args = _build_tool_arguments(
                    selected_tool_name=selected_edit_tool_name,
                    selected_tool=selected_edit_tool,
                    edit_payload=edit_payload,
                    user_query=user_query,
                )
                tool_call = {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": selected_edit_tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }
                trace["response"] = {
                    "content_preview": "",
                    "content_length_chars": 0,
                    "latency_ms": int((time.time() - stream_start_time) * 1000),
                    "tool_calls_count": 1,
                    "tool_calls": [tool_call],
                }
                set_current_trace(trace)

                def generate_sse_tool_call():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': tool_call['id'], 'type': 'function', 'function': {'name': selected_edit_tool_name, 'arguments': tool_call['function']['arguments']}}]}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]})}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    generate_sse_tool_call(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            if (not stream_tool_error) and (streamed_content or "").strip():
                # If tool JSON was not produced, do not drop content: return plain assistant text via SSE.
                trace["response"] = {
                    "content_preview": (streamed_content or "")[:log_preview],
                    "content_length_chars": len(streamed_content or ""),
                    "latency_ms": int((time.time() - stream_start_time) * 1000),
                    "tool_calls_count": 0,
                }
                set_current_trace(trace)

                def generate_sse_plain_text():
                    oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {'content': streamed_content}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(
                    generate_sse_plain_text(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

        if stream:
            set_proxy_status(STATUS_RESPONSE)
            def generate_sse():
                oid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                preview = ""
                stream_start_time = time.time()
                full_response = ""
                total_tokens_holder = [0]
                try:
                    for content in chat_client.stream_chat(ollama_messages, use_model):
                        if content:
                            full_response += content
                            preview += content[: max(0, log_preview - len(preview))]
                            chunk = {
                                "id": oid,
                                "object": "chat.completion.chunk",
                                "model": use_model,
                                "choices": [
                                    {"index": 0, "delta": {"content": content}, "finish_reason": None},
                                ],
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                    
                    # Log streaming request
                    stream_latency_ms = int((time.time() - stream_start_time) * 1000)
                    def _approx_tokens(text: str) -> int:
                        if not text:
                            return 0
                        return max(1, int(len(text) / 4))
                    
                    prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
                    prompt_tokens_approx = _approx_tokens(prompt_text)
                    completion_tokens_approx = _approx_tokens(full_response)
                    total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
                    total_tokens_holder[0] = total_tokens_approx

                    # Finalize trace for the UI and history
                    trace["ollama"]["tokens_estimates"] = {
                        "prompt_tokens_estimated": prompt_tokens_approx,
                        "completion_tokens_estimated": completion_tokens_approx,
                        "total_tokens_estimated": total_tokens_approx,
                    }
                    trace["response"] = {
                        "content_preview": full_response[:log_preview]
                        + ("..." if len(full_response) > log_preview else ""),
                        "content_length_chars": len(full_response),
                        "latency_ms": stream_latency_ms,
                    }
                    trace["steps"].append(
                        {
                            "name": "ollama_chat",
                            "duration_ms": int(stream_latency_ms),
                            "tokens_in_est": prompt_tokens_approx,
                            "tokens_out_est": completion_tokens_approx,
                        }
                    )
                    set_current_trace(trace)
                    
                    try:
                        session_manager = get_session_manager()
                        session = session_manager.get_or_create_session("proxy")
                        logs_repo = get_logs_repository()
                        log_metadata = {
                            "user_query": user_query[:500],
                            "response_preview": full_response[:500],
                            "trace_id": trace_id,
                            "model": use_model,
                            "latency_ms": stream_latency_ms,
                            "prompt_tokens": prompt_tokens_approx,
                            "completion_tokens": completion_tokens_approx,
                            "total_tokens": total_tokens_approx,
                            "rag_context": rag_context_data,
                            "rag_steps": rag_timings,
                            "trace": trace,
                            "stream": True,
                        }
                        logs_repo.add_log(
                            session_id="proxy",
                            level="INFO",
                            message=f"Proxy request (stream): {user_query[:100]}...",
                            source="proxy",
                            metadata=log_metadata,
                        )
                    except Exception as e:
                        _RAG_LOG.warning(f"Failed to log proxy stream request to database: {e}")
                    
                    _RAG_LOG.info(
                        "RAG response (stream) model=%s len=%s preview=%s",
                        use_model,
                        len(full_response),
                        preview[:log_preview] if preview else "",
                    )
                except Exception as e:
                    log_webui_error("rag_routes.chat_completions", e, {"stage": "stream_chat"})
                    _log_rag_error("stream_chat", e)
                    raise
                finally:
                    set_proxy_status(STATUS_IDLE)
                    set_latest_request_seconds(time.time() - start_time)
                    set_latest_request_total_tokens(total_tokens_holder[0] or None)
                yield f"data: {json.dumps({'id': oid, 'object': 'chat.completion.chunk', 'model': use_model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(
                generate_sse(),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            set_proxy_status(STATUS_RESPONSE)
            content = chat_client.chat(ollama_messages, use_model, stream=False, options=None)
        except Exception as e:
            log_webui_error("rag_routes.chat_completions", e, {"stage": "chat"})
            _log_rag_error("chat", e)
            return jsonify({"error": str(e)}), 500
        finally:
            set_proxy_status(STATUS_IDLE)
            set_latest_request_seconds(time.time() - start_time)
        latency_ms = int((time.time() - start_time) * 1000)
        _prompt_text = " ".join((m.get("content") or "") for m in ollama_messages if isinstance(m, dict))
        prompt_tokens_approx = max(1, int(len(_prompt_text) / 4))
        completion_tokens_approx = max(1, int(len(content or "") / 4))
        _total_tokens_approx = prompt_tokens_approx + completion_tokens_approx
        set_latest_request_total_tokens(_total_tokens_approx)
        content_len = len(content or "")
        content_preview = (content or "")[:log_preview]
        if content_len > log_preview:
            content_preview += "..."
        _RAG_LOG.info(
            "RAG response model=%s len=%s preview=%s",
            use_model,
            content_len,
            content_preview,
        )
        trace["ollama"]["tokens_estimates"] = {
            "prompt_tokens_estimated": prompt_tokens_approx,
            "completion_tokens_estimated": completion_tokens_approx,
            "total_tokens_estimated": _total_tokens_approx,
        }
        trace["response"] = {
            "content_preview": content_preview,
            "content_length_chars": content_len,
            "latency_ms": latency_ms,
        }
        trace["steps"].append(
            {
                "name": "ollama_chat",
                "duration_ms": int(latency_ms),
                "tokens_in_est": prompt_tokens_approx,
                "tokens_out_est": completion_tokens_approx,
            }
        )
        set_current_trace(trace)
        tool_calls: list[dict[str, object]] = []
        if (not stream) and tools and tool_choice != "none" and not has_tool_result:
            edit_payload = _extract_edit_from_response(content or "")
            if edit_payload and selected_edit_tool_name and selected_edit_tool:
                tool_args = _build_tool_arguments(
                    selected_tool_name=selected_edit_tool_name,
                    selected_tool=selected_edit_tool,
                    edit_payload=edit_payload,
                    user_query=user_query,
                )
                tool_calls = [
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": selected_edit_tool_name,
                            "arguments": json.dumps(tool_args, ensure_ascii=False),
                        },
                    }
                ]

        trace["response"]["tool_calls_count"] = len(tool_calls)
        if tool_calls:
            trace["response"]["tool_calls"] = tool_calls
            set_current_trace(trace)
        choice = {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None if tool_calls else content,
                **({"tool_calls": tool_calls} if tool_calls else {}),
            },
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }
        response_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": 0,
            "model": use_model,
            "choices": [choice],
        }
        
        # Add RAG metadata if requested
        if include_rag_metadata and rag_ctx:
            response_data["rag_metadata"] = {
                "chunks_info": rag_ctx.chunks_info,
                "max_score": rag_ctx.max_score,
                "chunks_count": len(rag_ctx.chunks_info),
            }

        # Persist trace for non-stream requests
        try:
            session_manager = get_session_manager()
            session = session_manager.get_or_create_session("proxy")
            logs_repo = get_logs_repository()
            log_metadata = {
                "user_query": user_query[:500],
                "response_preview": content_preview[:500],
                "trace_id": trace_id,
                "model": use_model,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens_approx,
                "completion_tokens": completion_tokens_approx,
                "total_tokens": _total_tokens_approx,
                "rag_context": rag_context_data,
                "rag_steps": rag_timings,
                "trace": trace,
                "stream": False,
            }
            logs_repo.add_log(
                session_id="proxy",
                level="INFO",
                message=f"Proxy request: {user_query[:100]}...",
                source="proxy",
                metadata=log_metadata,
            )
        except Exception as e:
            _RAG_LOG.warning(f"Failed to log proxy non-stream request to database: {e}")
        
        return jsonify(response_data)

    # Open WebUI status/start/stop: same pattern as RAG (docker), registered on app so always available
    from api.http.webui_routes import (
        open_webui_status,
        open_webui_start,
        open_webui_stop,
        webui_bp,
    )
    app.add_url_rule(
        "/api/webui/open-webui/status",
        view_func=open_webui_status,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/start",
        view_func=open_webui_start,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/webui/open-webui/stop",
        view_func=open_webui_stop,
        methods=["POST"],
    )

    app.register_blueprint(webui_bp)

    @app.route("/v1/files/apply-edit", methods=["POST"])
    def apply_file_edit() -> Response | tuple[Response, int]:
        """
        Apply direct file edit inside workspace by explicit line/column range.
        Expected body: { file_path, range:{start_line,start_col,end_line,end_col}, new_text, dry_run? }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception:
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400

        try:
            file_path_raw = str(body.get("file_path") or "").strip()
            range_data = body.get("range") or {}
            new_text = body.get("new_text")
            patch_text = body.get("patch")
            dry_run = bool(body.get("dry_run", False))
            if patch_text:
                return jsonify({"ok": False, "error": "patch apply is not supported yet"}), 400
            if not isinstance(range_data, dict):
                return jsonify({"ok": False, "error": "range must be an object"}), 400
            if not isinstance(new_text, str):
                return jsonify({"ok": False, "error": "new_text is required"}), 400

            resolved = _resolve_workspace_path(file_path_raw)
            if not resolved.exists():
                return jsonify({"ok": False, "error": "file does not exist"}), 404
            original = resolved.read_text(encoding="utf-8")

            # If end_col is huge (inferred unknown), clamp to line length + 1.
            if "end_col" in range_data:
                lines = original.splitlines(keepends=True)
                end_line = int(range_data.get("end_line") or 0)
                if 1 <= end_line <= len(lines):
                    end_col = int(range_data.get("end_col") or 1)
                    if end_col > len(lines[end_line - 1]) + 1:
                        range_data = dict(range_data)
                        range_data["end_col"] = len(lines[end_line - 1]) + 1

            updated = _replace_text_range(original, range_data, new_text)
            if not dry_run:
                resolved.write_text(updated, encoding="utf-8")
            try:
                get_logs_repository().add_log(
                    session_id="proxy",
                    level="INFO",
                    message=f"Apply edit: {resolved}",
                    source="proxy.apply_edit",
                    metadata={
                        "file_path": str(resolved),
                        "dry_run": dry_run,
                        "range": range_data,
                        "new_text_len": len(new_text),
                    },
                )
            except Exception:
                pass

            return jsonify(
                {
                    "ok": True,
                    "applied": not dry_run,
                    "dry_run": dry_run,
                    "file_path": str(resolved),
                    "preview": updated[:2000],
                }
            )
        except ValueError as exc:
            try:
                get_logs_repository().add_log(
                    session_id="proxy",
                    level="ERROR",
                    message=f"Apply edit failed: {exc}",
                    source="proxy.apply_edit",
                    metadata={"error": str(exc)},
                )
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            _RAG_LOG.exception("apply-file-edit failed")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/v1/external-docs/ingest", methods=["POST"])
    def external_docs_ingest() -> tuple[Response, int]:
        """Trigger ingest of an external source (e.g. tm_architecture) into its collection."""
        if not _EXTERNAL_DOCS_RAG_AVAILABLE:
            return jsonify({"error": "external_docs_rag module not available"}), 503
        try:
            body = request.get_json(force=True, silent=True) or {}
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400
        source_id = (body.get("source_id") or "").strip()
        if not source_id:
            return jsonify({"error": "source_id is required"}), 400
        try:
            from external_docs_rag.config_loader import load_external_sources
            from external_docs_rag.application.use_cases import ingest_source_to_collection
            from external_docs_rag.infrastructure import HttpFetchClient, QdrantChunkSink
            from external_docs_rag.infrastructure.ollama_embed_adapter import OllamaEmbedAdapter
            import os
            sources = load_external_sources()
            source = next((s for s in sources if s.id == source_id), None)
            if not source:
                return jsonify({"error": f"Source '{source_id}' not found"}), 404
            try:
                qdrant_url = get_qdrant_url()
            except Exception:
                qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            result = ingest_source_to_collection(
                source,
                HttpFetchClient(),
                QdrantChunkSink(base_url=qdrant_url),
                OllamaEmbedAdapter(),
            )
            return jsonify({
                "source_id": result.source_id,
                "collection_name": result.collection_name,
                "documents_fetched": result.documents_fetched,
                "chunks_indexed": result.chunks_indexed,
                "errors": result.errors,
            }), 200
        except Exception as e:
            _RAG_LOG.exception("external-docs ingest failed: %s", e)
            return jsonify({"error": str(e)}), 500

    return app


__all__ = ["create_app"]
