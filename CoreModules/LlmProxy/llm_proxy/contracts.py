"""Public wiring types for the LLM proxy module (no Chiron imports)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from llm_proxy.config import LlmProxyRuntimeConfig


@dataclass(frozen=True)
class LlmProxyBaseContext:
    """Per-app defaults from the first `get_rag_answer_params` (host fills from container)."""

    webui_dir: str | None
    system_prefix: str | None
    system_suffix: str | None
    prefix: str
    suffix: str
    context_chunk_chars: int
    context_total_chars: int
    confidence_threshold: float
    ollama_model: str
    log_preview: int
    rag_repo: Any
    embed_provider: Any
    rerank_client: Any
    chat_client: Any


@dataclass(frozen=True)
class LlmProxyExternalDocsBundle:
    """Optional hooks for external_docs_rag (merged retrieval, background ingest)."""

    available: bool = False
    load_rag_sources_config: Callable[[], Any] | None = None
    load_external_sources: Callable[[], Any] | None = None
    load_github_repos: Callable[[], Any] | None = None
    resolve_rag_sources_for_request: Callable[..., Any] | None = None
    build_merged_rag_context: Callable[..., Any] | None = None
    ingest_github_repo_markdown: Callable[..., Any] | None = None
    get_latest_release_tag: Callable[[str], str | None] | None = None
    http_fetch_client_cls: Any | None = None
    qdrant_chunk_sink_cls: Any | None = None
    qdrant_rag_search_adapter_cls: Any | None = None


@dataclass(frozen=True)
class LlmProxyWiring:
    """All host-provided dependencies; built in `api/http/llm_proxy_wiring.py`."""

    runtime: LlmProxyRuntimeConfig
    base: LlmProxyBaseContext
    workspace_root: Callable[..., Any]

    log_webui_error: Callable[[str, Exception, dict[str, Any]], None]
    get_settings_repository: Callable[[], Any]
    get_session_manager: Callable[[], Any]
    get_logs_repository: Callable[[], Any]

    set_proxy_status: Callable[[str], None]
    set_latest_request_seconds: Callable[[float], None]
    set_latest_request_total_tokens: Callable[[int | None], None]
    set_latest_request_rag_steps: Callable[[dict[str, float] | None], None]
    set_current_trace: Callable[[dict[str, Any]], None]

    status_idle: str
    status_rag_search: str
    status_preparing_response: str
    status_response: str

    check_collection_freshness: Callable[..., Any]
    get_rag_answer_params: Callable[..., tuple[Any, Any]]
    get_proxy_rerank_enabled: Callable[[], bool]
    get_qdrant_url: Callable[[], str]
    get_framework_collection_ttl_days: Callable[[], int]
    get_rag_required_keywords: Callable[[], list[str] | None]

    rag_prompt_file_exists: Callable[[str], bool]
    get_rag_prompt_prefix_suffix: Callable[[str], tuple[str, str]]

    build_rag_context: Callable[..., Any]
    prepare_ollama_messages: Callable[..., Any]
    determine_reasoning_level: Callable[..., Any]
    last_user_content: Callable[..., Any]

    rag_context_factory: Callable[..., Any]
    rag_question_request_factory: Callable[..., Any]

    get_autocomplete_ollama_model: Callable[[], str | None]
    """Resolved Ollama tag for autocomplete logical id (env / WebUI); None if unset."""

    llm_runtime: Any | None = None
    provider_registry: Any | None = None
    extension_manager: Any | None = None
    default_provider_id: str | None = None

    external_docs: LlmProxyExternalDocsBundle = field(default_factory=LlmProxyExternalDocsBundle)

    ingest_external_source: Callable[[str], tuple[dict[str, Any], int]] | None = None
    """POST /v1/external-docs/ingest: returns (json_dict, http_status). None -> 503."""

    build_web_supplement_for_proxy: Callable[[str, float, float, dict[str, Any]], tuple[str | None, dict[str, Any]]] | None = None
    """Optional (last_user, max_score, confidence_threshold, proxy_settings) -> (supplement text or None, trace meta)."""
