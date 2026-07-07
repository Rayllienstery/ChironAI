"""
Flask routes for WebUI frontend.

Registers the WebUI blueprint and composes domain-specific route modules.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from core.bootstrap.import_paths import ensure_webui_composition_paths
from core.contracts.webui_api import WEBUI_URL_PREFIX

ensure_webui_composition_paths()

from application.rag.webui_retrieval_settings import (
    RAG_TRIGGER_HELP_ROWS,
    config_default_chat_model,
    config_default_embed_model,
    config_default_rerank_model,
    get_rag_required_keywords_from_module,
)
from application.rag.webui_retrieval_settings import (
    get_effective_rag_trigger_threshold as _get_effective_rag_trigger_threshold,
)
from infrastructure.database import get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from prompts_manager import PROMPTS_DIR, TRASH_DIR

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
from api.http.webui_help_routes import register_help_routes
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
from api.http.webui_providers_routes import register_providers_routes
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


def get_effective_rag_trigger_threshold() -> int:
    """Resolve threshold via WebUI settings repo (patchable in tests)."""
    return _get_effective_rag_trigger_threshold(get_settings_repository())


webui_bp = Blueprint("webui", __name__, url_prefix=WEBUI_URL_PREFIX)


@webui_bp.get("/health")
def webui_health():
    return jsonify({"status": "ok"}), 200


register_prompt_routes(webui_bp, prompts_dir=PROMPTS_DIR, trash_dir=TRASH_DIR, error_log=_ERROR_LOG)
register_extension_routes(webui_bp, error_log=_ERROR_LOG)
register_docker_routes(webui_bp, error_log=_ERROR_LOG)
register_session_routes(webui_bp, error_log=_ERROR_LOG)
register_server_routes(webui_bp, error_log=_ERROR_LOG)
register_version_routes(webui_bp, error_log=_ERROR_LOG)
register_help_routes(webui_bp, error_log=_ERROR_LOG)
register_providers_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    settings_repository_factory=get_settings_repository,
)
register_observability_routes(webui_bp, error_log=_ERROR_LOG)
register_dependencies_routes(webui_bp, error_log=_ERROR_LOG)
register_settings_routes(
    webui_bp,
    error_log=_ERROR_LOG,
    keyword_collections_repository_factory=get_keyword_collections_repository,
    get_effective_rag_trigger_threshold=get_effective_rag_trigger_threshold,
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
    config_default_embed_model=config_default_embed_model,
    config_default_rerank_model=config_default_rerank_model,
    get_effective_rag_trigger_threshold=get_effective_rag_trigger_threshold,
    get_rag_required_keywords_from_module=lambda: get_rag_required_keywords_from_module(
        get_keyword_collections_repository
    ),
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
    config_default_chat_model=config_default_chat_model,
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
    config_default_chat_model=config_default_chat_model,
)

__all__ = ["webui_bp", "get_settings_repository", "LLM_PROXY_BUILDS_APP_KEY"]
