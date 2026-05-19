"""
WebUI HTTP JSON contract.

The React app ([CoreModules/CoreUI/src/services/api.js](CoreModules/CoreUI/src/services/api.js))
calls ``GET/POST ...`` under this prefix. The Flask blueprint in
[api/http/webui_routes.py](api/http/webui_routes.py) must use the same ``WEBUI_URL_PREFIX``.

When [modules/webui_backend](modules/webui_backend) replaces the monolith, it should
expose the same paths and payload shapes for CoreUI (or version the API explicitly).
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

class OllamaModelEntry(TypedDict, total=False):
    """One item inside GET /models ``models`` array."""

    id: str
    name: str
    description: str
    size: int
    modified_at: str


class ModelsListResponse(TypedDict):
    """GET /models — CoreUI uses ``data.models ?? []``."""

    models: list[OllamaModelEntry]


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
    visibility: str


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


class ProviderHealthDTO(TypedDict, total=False):
    ok: bool
    status: str
    message: str
    details: dict[str, Any]


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
    "OllamaModelEntry",
    "ModelsListResponse",
    "PromptListItem",
    "PromptsListResponse",
    "PromptContentResponse",
    "ModelSettingsGetResponse",
    "ModelSettingsPostResponse",
    "LlmProxyStatusResponse",
    "OpenAiModelsUrls",
    "LlmProxyBuildRow",
    "LlmProxyBuildsGetResponse",
    "LlmProxyBuildsPutOkResponse",
    "ExtensionCardDTO",
    "InstalledExtensionDTO",
    "ProviderHealthDTO",
    "ExtensionUiSchemaDTO",
    "webui_abs_path",
]
