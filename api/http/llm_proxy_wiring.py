"""Build `LlmProxyWiring` for CoreModules/LlmProxy from ChironAI services."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from application.rag.params import RAGAnswerParams, RAGDependencies
from application.rag.proxy_settings_contract import (
    load_proxy_settings,
    resolve_proxy_rerank_enabled,
    resolve_web_interaction_flags,
)
from infrastructure.database import get_settings_repository
from llm_proxy.config import LlmProxyRuntimeConfig
from llm_proxy.contracts import LlmProxyBaseContext, LlmProxyExternalDocsBundle, LlmProxyWiring

try:
    from config import get_framework_collection_ttl_days, get_proxy_rerank_enabled, get_qdrant_url
except ImportError:
    get_proxy_rerank_enabled = lambda: False  # type: ignore[assignment,misc]
    get_qdrant_url = lambda: "http://localhost:6333"  # type: ignore[assignment,misc]
    get_framework_collection_ttl_days = lambda: 90  # type: ignore[assignment,misc]

from api.http.proxy_status import (
    STATUS_IDLE,
    STATUS_PREPARING_RESPONSE,
    STATUS_RAG_SEARCH,
    STATUS_RESPONSE,
    set_latest_request_rag_steps,
    set_latest_request_seconds,
    set_latest_request_total_tokens,
    set_proxy_status,
)
from api.http.proxy_trace import set_current_trace

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_RAG_SVC = os.path.join(_ROOT, "CoreModules", "RagService")
if os.path.isdir(_RAG_SVC) and _RAG_SVC not in sys.path:
    sys.path.insert(0, _RAG_SVC)
_MODULES_EXT_RAG = os.path.join(_ROOT, "modules", "external_docs_rag")
if _MODULES_EXT_RAG not in sys.path:
    sys.path.insert(0, _MODULES_EXT_RAG)

_WEBINTERACTION = os.path.join(_ROOT, "CoreModules", "WebInteraction")
if _WEBINTERACTION not in sys.path:
    sys.path.insert(0, _WEBINTERACTION)
_LLM_INTERACTOR = os.path.join(_ROOT, "CoreModules", "LlmInteractor")
if os.path.isdir(_LLM_INTERACTOR) and _LLM_INTERACTOR not in sys.path:
    sys.path.insert(0, _LLM_INTERACTOR)
_DOCKER_MANAGER = os.path.join(_ROOT, "CoreModules", "DockerManager")
if os.path.isdir(_DOCKER_MANAGER) and _DOCKER_MANAGER not in sys.path:
    sys.path.insert(0, _DOCKER_MANAGER)

try:
    from external_docs_rag.application.use_cases import (
        build_merged_rag_context,
        ingest_github_repo_markdown,
        ingest_source_to_collection,
        resolve_rag_sources_for_request,
    )
    from external_docs_rag.config_loader import load_external_sources, load_github_repos, load_rag_sources_config
    from external_docs_rag.infrastructure import HttpFetchClient, QdrantChunkSink, QdrantRagSearchAdapter
    from external_docs_rag.infrastructure.github_discovery import get_latest_release_tag

    _EXTERNAL_DOCS_RAG_AVAILABLE = True
except ImportError:
    build_merged_rag_context = None  # type: ignore[assignment,misc]
    resolve_rag_sources_for_request = None  # type: ignore[assignment,misc]
    load_rag_sources_config = None  # type: ignore[assignment,misc]
    load_external_sources = None  # type: ignore[assignment,misc]
    load_github_repos = None  # type: ignore[assignment,misc]
    ingest_github_repo_markdown = None  # type: ignore[assignment,misc]
    HttpFetchClient = None  # type: ignore[assignment,misc]
    QdrantChunkSink = None  # type: ignore[assignment,misc]
    QdrantRagSearchAdapter = None  # type: ignore[assignment,misc]
    get_latest_release_tag = None  # type: ignore[assignment,misc]
    ingest_source_to_collection = None  # type: ignore[assignment,misc]
    _EXTERNAL_DOCS_RAG_AVAILABLE = False

try:
    from rag_service.infrastructure.keyword_collections_sqlite import get_keyword_collections_repository
except ImportError:
    get_keyword_collections_repository = None  # type: ignore[assignment,misc]

_RAG_LOG = logging.getLogger("trag.rag")
DEFAULT_LLM_PROVIDER_ID = "ollama"


class _RuntimeResolvingChatClient:
    """Chat-client bridge that switches to the extension runtime once it is ready."""

    def __init__(
        self,
        *,
        delegate: Any,
        extension_manager: Any | None,
        runtime: Any | None,
        provider_id: str | None,
    ) -> None:
        self._delegate = delegate
        self._extension_manager = extension_manager
        self._runtime = runtime
        self._provider_id = provider_id or DEFAULT_LLM_PROVIDER_ID
        self._url = getattr(delegate, "_url", None)
        self._default_options = dict(getattr(delegate, "_default_options", None) or {})

    def _resolved_runtime(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        manager = self._extension_manager
        if manager is None:
            return None
        return getattr(manager, "runtime", None)

    def _client(self) -> Any:
        runtime = self._resolved_runtime()
        if runtime is None:
            return self._delegate
        from llm_interactor import RuntimeBackedChatClient  # noqa: PLC0415

        return RuntimeBackedChatClient(
            runtime,
            provider_id=self._provider_id,
            upstream_url=self._url,
            default_options=self._default_options,
            delegate=self._delegate,
        )

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._client().chat(*args, **kwargs)

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._client().stream_chat(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client(), name)


def _get_proxy_rerank_enabled_for_proxy() -> bool:
    """
    Single contract for /v1 rerank toggle.

    Priority:
    1. persisted `proxy_settings.rerank_for_rag` from DB (WebUI setting),
    2. fallback to static config/env `get_proxy_rerank_enabled()`.
    """
    try:
        repo = get_settings_repository()
    except Exception:
        repo = None
    if repo is None:
        try:
            return bool(get_proxy_rerank_enabled())
        except Exception:
            return False
    proxy_settings = load_proxy_settings(repo)
    enabled, _source = resolve_proxy_rerank_enabled(
        settings_repo=repo,
        proxy_settings=proxy_settings,
        fallback_getter=get_proxy_rerank_enabled,
    )
    return enabled


def build_web_supplement_for_proxy(
    last_user: str,
    max_score: float,
    confidence_threshold: float,
    proxy_settings: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    """
    Free DuckDuckGo snippets when Web Interaction settings + triggers allow.
    Returns (text_or_none, meta) for proxy trace.
    """
    meta: dict[str, Any] = {
        "trigger": "none",
        "used": False,
        "error": None,
        "snippets_chars": 0,
        "queries": [],
        "cache_hit": False,
        "fetch_used": False,
        "wikipedia_used": False,
        "ddg_news": False,
        "domains_top": [],
        "snippets_count": 0,
    }
    try:
        from web_interaction.config import ddg_news_enabled, ddg_region_for_message, max_results_default
        from web_interaction.fetch_excerpt import fetch_page_env_enabled
        from web_interaction.supplement import build_web_supplement_bundle, should_fetch_web_supplement
        from web_interaction.wikipedia_fallback import wikipedia_env_enabled
    except ImportError:
        return None, meta

    flags = resolve_web_interaction_flags(
        proxy_settings=proxy_settings,
        env_ddg_news=ddg_news_enabled(),
        env_fetch_page=fetch_page_env_enabled(),
        env_wikipedia=wikipedia_env_enabled(),
    )
    master = bool(flags["web_interaction_enabled"]["value"])
    on_kw = bool(flags["web_interaction_on_keywords"]["value"])
    on_fw = bool(flags["web_interaction_on_low_confidence_framework"]["value"])

    ok, trigger = should_fetch_web_supplement(
        last_user or "",
        master_enabled=master,
        on_keywords=on_kw,
        on_low_confidence_framework=on_fw,
        max_score=float(max_score or 0.0),
        confidence_threshold=float(confidence_threshold or 0.0),
    )
    meta["trigger"] = trigger
    if not ok:
        return None, meta
    try:
        n = max_results_default()
        enable_news = bool(flags["web_interaction_ddg_news"]["value"])
        enable_fetch = bool(flags["web_interaction_fetch_page"]["value"])
        enable_wiki = bool(flags["web_interaction_wikipedia"]["value"])
        text, dbg = build_web_supplement_bundle(
            (last_user or "").strip(),
            trigger=trigger,  # type: ignore[arg-type]
            max_n=n,
            region=ddg_region_for_message(last_user or ""),
            ddg_news=enable_news,
            fetch_page=enable_fetch,
            wikipedia=enable_wiki,
        )
        for k in (
            "queries",
            "cache_hit",
            "fetch_used",
            "wikipedia_used",
            "ddg_news",
            "domains_top",
            "snippets_count",
            "snippets_chars",
        ):
            if k in dbg:
                meta[k] = dbg[k]
        meta["settings_sources"] = {k: str(v.get("source") or "") for k, v in flags.items()}
        meta["settings_effective"] = {k: bool(v.get("value")) for k, v in flags.items()}
    except Exception as e:
        meta["error"] = str(e)
        _RAG_LOG.warning("web supplement fetch failed: %s", e)
        return None, meta
    if not (text or "").strip():
        return None, meta
    meta["used"] = True
    meta["snippets_chars"] = len(text)
    return text, meta


def _get_rag_required_keywords_from_module() -> list[str] | None:
    if get_keyword_collections_repository is None:
        return None
    try:
        repo = get_keyword_collections_repository()
        flat = repo.get_enabled_keywords_flat()
        return flat if flat else None
    except Exception:
        return None


def _workspace_root() -> Path:
    return Path(_ROOT).resolve()


def _external_docs_bundle() -> LlmProxyExternalDocsBundle:
    if not _EXTERNAL_DOCS_RAG_AVAILABLE:
        return LlmProxyExternalDocsBundle(available=False)
    return LlmProxyExternalDocsBundle(
        available=True,
        load_rag_sources_config=load_rag_sources_config,
        load_external_sources=load_external_sources,
        load_github_repos=load_github_repos,
        resolve_rag_sources_for_request=resolve_rag_sources_for_request,
        build_merged_rag_context=build_merged_rag_context,
        ingest_github_repo_markdown=ingest_github_repo_markdown,
        get_latest_release_tag=get_latest_release_tag,
        http_fetch_client_cls=HttpFetchClient,
        qdrant_chunk_sink_cls=QdrantChunkSink,
        qdrant_rag_search_adapter_cls=QdrantRagSearchAdapter,
    )


def _extension_runtime_getter(extension_manager: Any | None, llm_runtime: Any | None) -> Any | None:
    if llm_runtime is not None:
        return llm_runtime
    if extension_manager is None:
        return None
    return getattr(extension_manager, "runtime", None)


def _runtime_backed_embed_provider(
    *,
    delegate: Any,
    extension_manager: Any | None,
    llm_runtime: Any | None,
    provider_id: str | None,
) -> Any:
    if extension_manager is None and llm_runtime is None:
        return delegate
    from rag_service.infrastructure.provider_runtime import RuntimeBackedEmbeddingProvider  # noqa: PLC0415

    return RuntimeBackedEmbeddingProvider(
        runtime_getter=lambda: _extension_runtime_getter(extension_manager, llm_runtime),
        provider_id=provider_id or DEFAULT_LLM_PROVIDER_ID,
        delegate=delegate,
    )


def _runtime_backed_rerank_client(
    *,
    delegate: Any,
    extension_manager: Any | None,
    llm_runtime: Any | None,
    provider_id: str | None,
) -> Any:
    if extension_manager is None and llm_runtime is None:
        return delegate
    from rag_service.infrastructure.provider_runtime import RuntimeBackedRerankClient  # noqa: PLC0415

    return RuntimeBackedRerankClient(
        runtime_getter=lambda: _extension_runtime_getter(extension_manager, llm_runtime),
        provider_id=provider_id or DEFAULT_LLM_PROVIDER_ID,
        delegate=delegate,
    )


def _ingest_external_source(source_id: str, *, embed_provider: Any) -> tuple[dict[str, Any], int]:
    if not _EXTERNAL_DOCS_RAG_AVAILABLE or ingest_source_to_collection is None:
        return {"error": "external_docs_rag module not available"}, 503
    try:
        sources = load_external_sources()
        source = next((s for s in sources if s.id == source_id), None)
        if not source:
            return {"error": f"Source '{source_id}' not found"}, 404
        try:
            qdrant_url = get_qdrant_url()
        except Exception:
            qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        result = ingest_source_to_collection(
            source,
            HttpFetchClient(),
            QdrantChunkSink(base_url=qdrant_url),
            embed_provider,
        )
        return (
            {
                "source_id": result.source_id,
                "collection_name": result.collection_name,
                "documents_fetched": result.documents_fetched,
                "chunks_indexed": result.chunks_indexed,
                "errors": result.errors,
            },
            200,
        )
    except Exception as e:
        _RAG_LOG.exception("external-docs ingest failed: %s", e)
        return {"error": str(e)}, 500


def _get_autocomplete_provider_model() -> str | None:
    """Resolved provider model for ChironAI-Autocomplete logical id: env overrides WebUI."""
    env_m = (os.getenv("LLM_PROXY_AUTOCOMPLETE_OLLAMA_MODEL") or "").strip()
    if env_m:
        return env_m
    try:
        repo = get_settings_repository()
        return (repo.get_app_setting("proxy_autocomplete_model") or "").strip() or None
    except Exception:
        return None


def _build_extension_manager(
    *,
    deps: RAGDependencies,
) -> tuple[Any | None, Any | None, Any | None, Any | None, str | None]:
    try:
        from llm_interactor import (
            ExtensionManager,
            ExtensionRegistryClient,
            ProviderHostContext,
        )
    except Exception as e:
        _RAG_LOG.warning("LlmInteractor unavailable; falling back to direct chat client: %s", e)
        return None, None, None, None, None

    try:
        settings_repo = get_settings_repository()
    except Exception as e:
        _RAG_LOG.warning("settings repository unavailable for LlmInteractor: %s", e)
        return None, None, None, None, None
    try:
        from docker_manager import DockerManager

        docker_runtime = DockerManager()
    except Exception as e:
        _RAG_LOG.warning("DockerManager unavailable for LlmInteractor extensions: %s", e)
        docker_runtime = None

    def _stop_native_ollama() -> tuple[bool, str]:
        """Stop the native Ollama process on the host (Windows: taskkill; Linux: pkill)."""
        try:
            from api.http.service_control import ensure_servicestarter_on_path  # noqa: PLC0415

            ensure_servicestarter_on_path()
            from servicestarter.ollama_ops import stop_ollama_process  # noqa: PLC0415

            return stop_ollama_process()
        except Exception as exc:
            return False, str(exc)

    host_context = ProviderHostContext(
        project_root=_workspace_root(),
        get_settings_repository=get_settings_repository,
        chat_client=deps.chat_client,
        docker_runtime=docker_runtime,
        metadata={
            "source": "api.http.llm_proxy_wiring",
            "stop_native_ollama": _stop_native_ollama,
        },
    )
    manager = ExtensionManager(
        project_root=_workspace_root(),
        host_context=host_context,
        settings_repo=settings_repo,
        registry_client=ExtensionRegistryClient(project_root=_workspace_root()),
        default_provider_id=DEFAULT_LLM_PROVIDER_ID,
    )
    manager.start_background_bootstrap()
    runtime_chat_client = _RuntimeResolvingChatClient(
        delegate=deps.chat_client,
        extension_manager=manager,
        runtime=None,
        provider_id=DEFAULT_LLM_PROVIDER_ID,
    )
    _RAG_LOG.info("Extension runtime bootstrap started in background")
    return manager, None, None, runtime_chat_client, DEFAULT_LLM_PROVIDER_ID


def build_llm_proxy_wiring(
    *,
    params: RAGAnswerParams,
    deps: RAGDependencies,
    webui_dir: str | None,
    system_prefix: str | None,
    system_suffix: str | None,
) -> LlmProxyWiring:
    import api.http.rag_routes as rr

    prefix = system_prefix if system_prefix is not None else params.system_prefix
    suffix = system_suffix if system_suffix is not None else params.system_suffix
    extension_manager = None
    llm_runtime = None
    provider_registry = None
    runtime_chat_client = None
    default_provider_id = DEFAULT_LLM_PROVIDER_ID
    extension_manager, llm_runtime, provider_registry, runtime_chat_client, default_provider_id = _build_extension_manager(deps=deps)
    default_provider_id = default_provider_id or DEFAULT_LLM_PROVIDER_ID
    runtime_embed_provider = _runtime_backed_embed_provider(
        delegate=deps.embed_provider,
        extension_manager=extension_manager,
        llm_runtime=llm_runtime,
        provider_id=default_provider_id,
    )
    runtime_rerank_client = _runtime_backed_rerank_client(
        delegate=deps.rerank_client,
        extension_manager=extension_manager,
        llm_runtime=llm_runtime,
        provider_id=default_provider_id,
    )
    return LlmProxyWiring(
        runtime=LlmProxyRuntimeConfig.from_env(),
        base=LlmProxyBaseContext(
            webui_dir=webui_dir,
            system_prefix=system_prefix,
            system_suffix=system_suffix,
            prefix=prefix,
            suffix=suffix,
            context_chunk_chars=params.context_chunk_chars,
            context_total_chars=params.context_total_chars,
            confidence_threshold=params.confidence_threshold,
            ollama_model=params.model_name,
            log_preview=params.log_preview_chars,
            rag_repo=deps.rag_repo,
            embed_provider=runtime_embed_provider,
            rerank_client=runtime_rerank_client,
            chat_client=runtime_chat_client or deps.chat_client,
        ),
        workspace_root=_workspace_root,
        log_webui_error=rr.log_webui_error,
        get_settings_repository=rr.get_settings_repository,
        get_session_manager=rr.get_session_manager,
        get_logs_repository=rr.get_logs_repository,
        set_proxy_status=set_proxy_status,
        set_latest_request_seconds=set_latest_request_seconds,
        set_latest_request_total_tokens=set_latest_request_total_tokens,
        set_latest_request_rag_steps=set_latest_request_rag_steps,
        set_current_trace=set_current_trace,
        status_idle=STATUS_IDLE,
        status_rag_search=STATUS_RAG_SEARCH,
        status_preparing_response=STATUS_PREPARING_RESPONSE,
        status_response=STATUS_RESPONSE,
        check_collection_freshness=rr.check_collection_freshness,
        get_rag_answer_params=rr.get_rag_answer_params,
        get_proxy_rerank_enabled=_get_proxy_rerank_enabled_for_proxy,
        get_qdrant_url=rr.get_qdrant_url,
        get_framework_collection_ttl_days=rr.get_framework_collection_ttl_days,
        get_rag_required_keywords=_get_rag_required_keywords_from_module,
        rag_prompt_file_exists=rr.rag_prompt_file_exists,
        get_rag_prompt_prefix_suffix=rr.get_rag_system_prompt,
        build_rag_context=rr.build_rag_context,
        prepare_ollama_messages=rr.prepare_ollama_messages,
        determine_reasoning_level=rr.determine_reasoning_level,
        last_user_content=rr.last_user_content,
        rag_context_factory=rr.RagContext,
        rag_question_request_factory=rr.RagQuestionRequest,
        get_autocomplete_ollama_model=_get_autocomplete_provider_model,
        llm_runtime=llm_runtime,
        provider_registry=provider_registry,
        extension_manager=extension_manager,
        default_provider_id=default_provider_id,
        external_docs=_external_docs_bundle(),
        ingest_external_source=lambda source_id: _ingest_external_source(
            source_id,
            embed_provider=runtime_embed_provider,
        ),
        build_web_supplement_for_proxy=build_web_supplement_for_proxy,
    )
