"""
Flask routes for WebUI frontend.

Registers the WebUI blueprint and composes domain-specific route modules.
"""

from __future__ import annotations

import logging

from flask import Blueprint

from core.bootstrap.import_paths import ensure_webui_composition_paths
from core.contracts.webui_api import WEBUI_URL_PREFIX

ensure_webui_composition_paths()

from config import get_retrieval_int
from config.rag_prompts import PROMPTS_DIR, TRASH_DIR
from infrastructure.database import get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger

try:
    from rag_service.infrastructure.keyword_collections_sqlite import get_keyword_collections_repository
except ImportError:
    get_keyword_collections_repository = None  # type: ignore[assignment]

try:
    from external_docs_rag.application.use_cases import (  # noqa: F401
        build_merged_rag_context,
        ingest_github_repo_markdown,
        resolve_rag_sources_for_request,
    )

    _EXTERNAL_DOCS_RAG_AVAILABLE = True
except ImportError:
    _EXTERNAL_DOCS_RAG_AVAILABLE = False

try:
    from modules.md_indexer import (
        get_active_pipeline_name,
        run_pipeline,
    )
except ImportError:
    get_active_pipeline_name = None  # type: ignore[assignment]
    run_pipeline = None  # type: ignore[assignment]

from api.http.proxy_status import set_latest_request_seconds, set_proxy_status
from api.http.webui_chat_routes import register_chat_routes
from api.http.webui_crawler_routes import register_crawler_routes
from api.http.webui_dependencies_routes import register_dependencies_routes
from api.http.webui_docker_routes import register_docker_routes
from api.http.webui_extensions_routes import register_extension_routes
from api.http.webui_llm_proxy_routes import register_llm_proxy_routes
from api.http.webui_model_tester_routes import register_model_tester_routes
from api.http.webui_observability_routes import register_observability_routes
from api.http.webui_performance_routes import register_performance_routes
from api.http.webui_prompt_routes import register_prompt_routes
from api.http.webui_provider_helpers import (
    default_llm_provider_id as _default_llm_provider_id,
)
from api.http.webui_provider_helpers import (
    default_provider_row as _default_provider_row,
)
from api.http.webui_provider_helpers import (
    provider_catalog_payload as _provider_catalog_payload,
)
from api.http.webui_provider_helpers import (
    read_app_provider_model_ref as _read_app_provider_model_ref,
)
from api.http.webui_provider_helpers import (
    run_unified_proxy_chat as _run_unified_proxy_chat,
)
from api.http.webui_rag_routes import (
    get_qdrant_collection_names as _get_qdrant_collection_names,
)
from api.http.webui_rag_routes import (
    register_rag_pipeline_routes,
    register_rag_qdrant_routes,
)
from api.http.webui_server_routes import register_server_routes
from api.http.webui_session_routes import register_session_routes
from api.http.webui_settings_routes import register_settings_routes
from api.http.webui_testing_routes import register_testing_routes
from api.http.webui_version_routes import register_version_routes
from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY
_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

# Compatibility hook for older tests/integrations that monkeypatch this name.
_enrich_builds_with_diagnostics = None

webui_bp = Blueprint("webui", __name__, url_prefix=WEBUI_URL_PREFIX)


def _get_rag_required_keywords_from_module() -> list[str] | None:
    if get_keyword_collections_repository is None:
        return None
    try:
        repo = get_keyword_collections_repository()
        flat = repo.get_enabled_keywords_flat()
        return flat if flat else None
    except Exception:
        return None


def _get_effective_rag_trigger_threshold() -> int:
    try:
        settings_repo = get_settings_repository()
        raw = settings_repo.get_app_setting("rag_trigger_threshold")
        if raw is not None and str(raw).strip() != "":
            return int(raw)
    except Exception:
        pass
    return get_retrieval_int("rag_trigger_threshold", 2)


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


def _config_default_chat_model() -> str:
    try:
        from config import get_default_chat_model

        return str(get_default_chat_model() or "").strip()
    except Exception:
        return ""


def _config_default_embed_model() -> str:
    try:
        from config import get_default_embed_model

        return str(get_default_embed_model() or "").strip()
    except Exception:
        return ""


def _config_default_rerank_model() -> str:
    try:
        from config import get_default_rerank_model

        return str(get_default_rerank_model() or "").strip()
    except Exception:
        return ""


register_prompt_routes(webui_bp, prompts_dir=PROMPTS_DIR, trash_dir=TRASH_DIR, error_log=_ERROR_LOG)
register_extension_routes(webui_bp, error_log=_ERROR_LOG)
register_docker_routes(webui_bp, error_log=_ERROR_LOG)
register_session_routes(webui_bp, error_log=_ERROR_LOG)
register_server_routes(webui_bp, error_log=_ERROR_LOG)
register_version_routes(webui_bp, error_log=_ERROR_LOG)
register_observability_routes(webui_bp, error_log=_ERROR_LOG)
register_dependencies_routes(webui_bp, error_log=_ERROR_LOG)
register_settings_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    keyword_collections_repository_factory=get_keyword_collections_repository,
    get_effective_rag_trigger_threshold=_get_effective_rag_trigger_threshold,
    trigger_help_rows=RAG_TRIGGER_HELP_ROWS,
)
register_llm_proxy_routes(webui_bp, error_log=_ERROR_LOG)
register_crawler_routes(webui_bp, error_log=_ERROR_LOG)
register_performance_routes(webui_bp)
register_testing_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    external_docs_rag_available=_EXTERNAL_DOCS_RAG_AVAILABLE,
    run_pipeline=run_pipeline,
    get_active_pipeline_name=get_active_pipeline_name,
)
register_rag_pipeline_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    default_llm_provider_id=_default_llm_provider_id,
    read_app_provider_model_ref=_read_app_provider_model_ref,
    config_default_embed_model=_config_default_embed_model,
    config_default_rerank_model=_config_default_rerank_model,
    get_effective_rag_trigger_threshold=_get_effective_rag_trigger_threshold,
    get_rag_required_keywords_from_module=_get_rag_required_keywords_from_module,
)
register_rag_qdrant_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    default_provider_row=_default_provider_row,
)
register_chat_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    provider_catalog_payload=_provider_catalog_payload,
    default_llm_provider_id=_default_llm_provider_id,
    config_default_chat_model=_config_default_chat_model,
    run_unified_proxy_chat=_run_unified_proxy_chat,
    set_proxy_status=set_proxy_status,
    set_latest_request_seconds=set_latest_request_seconds,
)
register_model_tester_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    run_unified_proxy_chat=_run_unified_proxy_chat,
    default_llm_provider_id=_default_llm_provider_id,
    read_app_provider_model_ref=_read_app_provider_model_ref,
    get_qdrant_collection_names=_get_qdrant_collection_names,
    config_default_chat_model=_config_default_chat_model,
)

__all__ = ["webui_bp", "get_settings_repository", "LLM_PROXY_BUILDS_APP_KEY"]
