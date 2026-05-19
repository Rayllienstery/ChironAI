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
_SECURITY = os.path.join(_ROOT, "CoreModules", "Security")
if os.path.isdir(_SECURITY) and _SECURITY not in sys.path:
    sys.path.insert(0, _SECURITY)
_DOCKER_MANAGER = os.path.join(_ROOT, "CoreModules", "DockerManager")
if os.path.isdir(_DOCKER_MANAGER) and _DOCKER_MANAGER not in sys.path:
    sys.path.insert(0, _DOCKER_MANAGER)
_ERROR_MANAGER = os.path.join(_ROOT, "CoreModules", "ErrorManager")
if os.path.isdir(_ERROR_MANAGER) and _ERROR_MANAGER not in sys.path:
    sys.path.insert(0, _ERROR_MANAGER)
_WEBUI_BACKEND = os.path.join(_ROOT, "CoreModules", "WebUIBackend")
if os.path.isdir(_WEBUI_BACKEND) and _WEBUI_BACKEND not in sys.path:
    sys.path.insert(0, _WEBUI_BACKEND)

from error_manager.exceptions import ValidationError as _ValidationError
from error_manager.http import error_response as _error_response
from webui_backend.paths import webui_data_dir

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
    get_settings_repository,
)
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from api.http.webui_crawler_routes import register_crawler_routes
from api.http.webui_docker_routes import register_docker_routes
from api.http.webui_extensions_routes import register_extension_routes
from api.http.webui_llm_proxy_routes import register_llm_proxy_routes
from api.http.webui_observability_routes import register_observability_routes
from api.http.webui_prompt_routes import register_prompt_routes
from api.http.webui_session_routes import register_session_routes
from api.http.webui_settings_routes import register_settings_routes
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
    get_current_trace,
)
from api.http.service_control import (
    start_qdrant as start_qdrant_service,
    stop_qdrant as stop_qdrant_service,
)

import requests

from infrastructure.ollama.cli_runner import (
    invoke_ping,
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

# Compatibility hook for older tests/integrations that monkeypatch this name
# through api.http.webui_routes after LLM Proxy routes moved to a domain module.
_enrich_builds_with_diagnostics = None

webui_bp = Blueprint("webui", __name__, url_prefix=WEBUI_URL_PREFIX)


def _register_extension_http_routes(bp: Blueprint) -> None:
    """Discover bundled extensions and register any extension-owned HTTP routes.

    Extensions that want to contribute routes expose a module-level function
    ``register_http_routes_on_blueprint(bp)`` in their ``backend/provider.py``.
    Route *handlers* close over ``current_app`` so they resolve the running
    extension at request time — no static coupling to a specific extension class.

    Discovery is purely filesystem-based: the project has zero import-time
    knowledge about which extensions are installed.
    """
    import importlib.util
    import pathlib

    here = pathlib.Path(__file__).parent.parent.parent  # project root
    bundled = here / "extensions" / "bundled"
    if not bundled.is_dir():
        return

    for ext_dir in sorted(bundled.iterdir()):
        if not ext_dir.is_dir():
            continue
        provider_py = ext_dir / "backend" / "provider.py"
        if not provider_py.is_file():
            continue
        try:
            mod_name = f"_ext_bp_{ext_dir.name}_provider"
            spec = importlib.util.spec_from_file_location(mod_name, provider_py)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            fn = getattr(mod, "register_http_routes_on_blueprint", None)
            if callable(fn):
                fn(bp)
        except Exception as _e:
            _WEBUI_LOG.warning("_register_extension_http_routes: %r: %s", ext_dir.name, _e)


register_prompt_routes(
    webui_bp,
    prompts_dir=PROMPTS_DIR,
    trash_dir=TRASH_DIR,
    error_log=_ERROR_LOG,
)
register_extension_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
register_docker_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
register_session_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
register_observability_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
register_settings_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    keyword_collections_repository_factory=get_keyword_collections_repository,
    get_effective_rag_trigger_threshold=lambda: _get_effective_rag_trigger_threshold(),
    trigger_help_rows=RAG_TRIGGER_HELP_ROWS,
)
register_llm_proxy_routes(
    webui_bp,
    error_log=_ERROR_LOG,
)
_register_extension_http_routes(webui_bp)
register_crawler_routes(
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
            webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
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
    provider_row = _default_provider_row()
    provider_health = provider_row.get("health") if isinstance(provider_row, dict) else None
    if isinstance(provider_health, dict):
        payload["ollama"] = {"running": bool(provider_health.get("ok"))}
    else:
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


__all__ = ["webui_bp"]
