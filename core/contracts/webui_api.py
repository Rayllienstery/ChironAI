"""
WebUI HTTP JSON contract.

The React app ([CoreModules/CoreUI/src/services/api.js](CoreModules/CoreUI/src/services/api.js))
calls ``GET/POST ...`` under this prefix. The canonical backend package is
[modules/webui_backend](modules/webui_backend); its Flask entrypoints and the
remaining route-composition modules under [api/http](api/http) must use the same
``WEBUI_URL_PREFIX`` and payload shapes for CoreUI (or version the API explicitly).
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# Must stay in sync with CoreUI ``API_BASE`` and Flask ``Blueprint(..., url_prefix=...)``.
WEBUI_URL_PREFIX: str = "/api/webui"


class WebUiErrorResponse(TypedDict):
    """Common error JSON for many WebUI routes (4xx/5xx)."""

    error: str


class WebUiValidationErrorResponse(TypedDict, total=False):
    """PUT /llm-proxy/builds and similar validation failures."""

    error: str
    details: list[str]


# --- Session -----------------------------------------------------------------

class SessionResponse(TypedDict, total=False):
    """GET /sessions — CoreUI expects ``id`` for localStorage."""

    id: str
    # Additional session fields may be present.


# --- Models & prompts --------------------------------------------------------

class ProviderModelEntry(TypedDict, total=False):
    """One item inside GET /models ``models`` array."""

    id: str
    name: str
    description: str
    size: int
    modified_at: str


class ModelsListResponse(TypedDict):
    """GET /models — CoreUI uses ``data.models ?? []``."""

    models: list[ProviderModelEntry]


class PromptListItem(TypedDict):
    name: str
    id: str


class PromptsListResponse(TypedDict):
    prompts: list[PromptListItem]


class PromptContentResponse(TypedDict):
    name: str
    content: str


class ModelSettingsGetResponse(TypedDict):
    """GET /model-settings — full persisted proxy + RAG UI state (all keys always present)."""

    model: str
    prompt_name: str
    temperature: float
    top_p: float
    reasoning_level: str
    code_only: bool
    include_rag_metadata: bool
    fetch_web_knowledge: bool
    web_interaction_enabled: bool
    web_interaction_on_keywords: bool
    web_interaction_on_low_confidence_framework: bool
    web_interaction_ddg_news: bool
    web_interaction_fetch_page: bool
    web_interaction_wikipedia: bool
    rag_collection: str
    autocomplete_model: str
    model_missing: bool
    prompt_missing: bool
    collection_missing: bool


class ModelSettingsPostResponse(TypedDict):
    """POST /model-settings — merges body into stored proxy_settings blob."""

    status: Literal["ok"]
    settings: dict[str, Any]


class AppSettingsResponse(TypedDict, total=False):
    """GET/POST /settings — app settings plus main server port metadata."""

    status: Literal["ok"]
    rag_collection: str
    server_port: int
    server_port_active: int
    server_port_source: Literal["env", "settings", "config", "default"]
    server_port_restart_required: bool


class CreateCollectionEmbeddingHistoryRow(TypedDict, total=False):
    """One recent create-collection file activity row."""

    source_id: str
    filename: str
    path: str
    chars: int
    chunks: int
    chunk_ms: int
    status: Literal["embedding", "skipped", "error"]
    reason: str
    detail: str


class CreateCollectionStatusResponse(TypedDict, total=False):
    """GET /crawler/create-collection-status/{job_id}."""

    job_id: str
    status: Literal["running", "success", "failed", "cancelled", "started"]
    collection_name: str
    source_ids: list[str]
    processed_pages: int
    total_pages: int
    indexed_pages: int
    prepared_pages: int
    total_chunks: int
    prepared_chunks: int
    skipped_pages: int
    skip_reasons: dict[str, int]
    current_source_id: str
    current_filename: str
    current_phase: str
    current_phase_elapsed_ms: int
    elapsed_ms: int
    phase_durations_ms: dict[str, int]
    current_embedding_chars: int
    current_embedding_chunks: int
    current_embedding_chunk_ms: int
    embedding_history: list[CreateCollectionEmbeddingHistoryRow]
    parallel_embed_workers: int
    errors: list[str]
    recent_skips: list[dict[str, Any]]
    skip_log: list[dict[str, Any]]
    skip_log_count: int
    statistics: dict[str, Any]
    error: str | None


class LlmProxyStatusResponse(TypedDict):
    """GET /llm-proxy/status — card “Fusion Proxy” in CoreUI."""

    enabled: bool
    base_url: str
    health: str


class OpenAiModelsUrls(TypedDict):
    main: str


class LlmProxyBuildRow(TypedDict, total=False):
    """One build after ``_enrich_builds_with_diagnostics`` (subset; extra keys allowed)."""

    id: str
    label: str
    backend: str
    model: str
    prompt_name: str
    use_prompt_template: bool
    issues: list[str]
    healthy: bool


class LlmProxyBuildsGetResponse(TypedDict):
    """GET /llm-proxy/builds."""

    builds: list[LlmProxyBuildRow]
    openai_models_urls: OpenAiModelsUrls


class LlmProxyBuildsPutOkResponse(TypedDict):
    """PUT /llm-proxy/builds success."""

    ok: Literal[True]
    builds: list[LlmProxyBuildRow]


class ExtensionCardDTO(TypedDict, total=False):
    id: str
    title: str
    description: str
    icon: str
    latest_version: str
    repository: str
    repository_id: str
    publisher: dict[str, Any]
    capabilities: list[dict[str, Any]]
    blocklist: dict[str, Any]
    visibility: str


class ExtensionDetailsDTO(TypedDict, total=False):
    """GET /extensions/{extension_id}/details."""

    entry: ExtensionCardDTO
    versions: list[dict[str, Any]]
    latest: dict[str, Any]
    readme: dict[str, Any]
    publisher: dict[str, Any]
    warnings: list[str]


class ExtensionDockerStatusDTO(TypedDict, total=False):
    container_name: str
    image: str
    running: bool
    volumes: list[str]
    data_persisted: bool
    update_status: str
    update_available: bool
    update_message: str
    remote_digest: str
    current_version: str
    update_version: str


class InstalledExtensionDTO(TypedDict, total=False):
    id: str
    version: str
    enabled: bool
    installed: bool
    restart_required: bool
    status: str
    error: str
    security_blocked: bool
    security_findings: list[dict[str, Any]]
    blocklist: dict[str, Any]
    sandboxed: bool
    sandbox_status: str
    sandbox_error: str
    docker: ExtensionDockerStatusDTO


class ProviderHealthDTO(TypedDict, total=False):
    ok: bool
    status: str
    message: str
    details: dict[str, Any]


class StartupStep(TypedDict, total=False):
    """One sub-step within a StartupPhase."""

    id: str
    label: str
    description: str
    start_offset_ms: float
    duration_ms: float
    status: str  # "ok" | "failed" | "in_progress" | "skipped"


class StartupPhase(TypedDict, total=False):
    """One top-level startup phase (e.g. Flask App Init, Session Manager)."""

    id: str
    label: str
    description: str
    start_offset_ms: float
    duration_ms: float
    status: str
    steps: list[StartupStep]
    log_lines: list[str]
    metadata: dict[str, Any]


class StartupPerformanceResponse(TypedDict, total=False):
    """GET /api/webui/performance/startup response."""

    server_start_epoch_ms: float
    total_duration_ms: float
    phases: list[StartupPhase]
    browser_timing: dict[str, Any]


class DependencySourceDTO(TypedDict, total=False):
    path: str
    group: str
    requested: str


class DependencyDTO(TypedDict, total=False):
    id: str
    ecosystem: Literal["python", "npm", "docker"]
    name: str
    requested: str
    installed_version: str | None
    latest_version: str | None
    status: Literal["installed", "missing", "declared"]
    manager: str
    sources: list[DependencySourceDTO]


class DependencyCountsDTO(TypedDict, total=False):
    total: int
    installed: int
    missing: int
    declared: int
    python: int
    npm: int
    docker: int


class DependencyCapabilityDTO(TypedDict, total=False):
    id: Literal["check", "update_all"]
    label: str
    commands: list[str]


class DependenciesResponse(TypedDict, total=False):
    dependencies: list[DependencyDTO]
    counts: DependencyCountsDTO
    files: list[str]
    generated_at: str
    update_capabilities: list[DependencyCapabilityDTO]


class DependencyProgressEntryDTO(TypedDict, total=False):
    name: str
    phase: str
    current: str | None
    next_version: str | None
    status: Literal["started", "done", "failed"]


class DependencyJobStepDTO(TypedDict, total=False):
    command: str
    cwd: str
    returncode: int | None
    ok: bool
    duration_ms: float
    output: str
    phase: str
    completed_packages: list[str]


class DependencyJobDTO(TypedDict, total=False):
    id: str
    mode: Literal["check", "update_all"]
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: str
    started_at: str | None
    finished_at: str | None
    steps: list[DependencyJobStepDTO]
    result: dict[str, Any] | None
    current_phase: str
    current_package: str
    current_ecosystem: str
    current_detail: str
    updated_packages: list[DependencyProgressEntryDTO]


class DependencyJobResponse(TypedDict):
    job: DependencyJobDTO


class ExtensionUiSchemaDTO(TypedDict, total=False):
    id: str
    title: str
    description: str
    icon: str
    settings_schema: dict[str, Any]
    ui_schema: dict[str, Any]


def webui_abs_path(suffix: str) -> str:
    """``suffix`` starts with ``/`` (e.g. ``/models``)."""
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    return f"{WEBUI_URL_PREFIX}{suffix}"


__all__ = [
    "WEBUI_URL_PREFIX",
    "WebUiErrorResponse",
    "WebUiValidationErrorResponse",
    "SessionResponse",
    "ProviderModelEntry",
    "ModelsListResponse",
    "PromptListItem",
    "PromptsListResponse",
    "PromptContentResponse",
    "ModelSettingsGetResponse",
    "ModelSettingsPostResponse",
    "AppSettingsResponse",
    "LlmProxyStatusResponse",
    "OpenAiModelsUrls",
    "LlmProxyBuildRow",
    "LlmProxyBuildsGetResponse",
    "LlmProxyBuildsPutOkResponse",
    "ExtensionCardDTO",
    "ExtensionDetailsDTO",
    "ExtensionDockerStatusDTO",
    "InstalledExtensionDTO",
    "ProviderHealthDTO",
    "ExtensionUiSchemaDTO",
    "StartupStep",
    "StartupPhase",
    "StartupPerformanceResponse",
    "DependencySourceDTO",
    "DependencyDTO",
    "DependencyCountsDTO",
    "DependencyCapabilityDTO",
    "DependenciesResponse",
    "DependencyJobStepDTO",
    "DependencyJobDTO",
    "DependencyJobResponse",
    "DependencyProgressEntryDTO",
    "webui_abs_path",
]
