"""OpenAPI and Swagger UI routes for Flask applications."""
# pyright: reportUnusedFunction=false

from __future__ import annotations

import re
from copy import deepcopy
from importlib import resources
from typing import Any, cast

from flask import Flask, Response, abort, current_app, jsonify, render_template_string, send_file

from core.contracts.webui_api import WEBUI_URL_PREFIX
from core.version import APP_NAME, APP_STAGE, VERSION

_PATH_PARAM_RE = re.compile(r"<(?:(?P<converter>[a-zA-Z_][\w]*):)?(?P<name>[a-zA-Z_][\w]*)>")
_INTERNAL_ENDPOINT_SUFFIXES = {
    "static",
    "swagger_ui",
    "swagger_asset",
    "swagger_openapi_json",
    "openapi_json",
}


def _openapi_path(flask_rule: str) -> str:
    return _PATH_PARAM_RE.sub(lambda match: "{" + match.group("name") + "}", flask_rule)


def _path_parameters(flask_rule: str) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    for match in _PATH_PARAM_RE.finditer(flask_rule):
        converter = match.group("converter") or "string"
        schema_type = "integer" if converter in {"int", "integer"} else "string"
        params.append(
            {
                "name": match.group("name"),
                "in": "path",
                "required": True,
                "schema": {"type": schema_type},
            }
        )
    return params


def _tag_for_path(path: str) -> str:
    if path == "/":
        return "root"
    parts = [part for part in path.strip("/").split("/") if part]
    if parts[:2] == ["api", "webui"] and len(parts) > 2:
        return parts[2].replace("-", " ").title()
    if parts and parts[0] == "v1":
        return "Llm Proxy"
    return (parts[0] if parts else "root").replace("-", " ").title()


_OPERATION_DETAILS: dict[tuple[str, str], dict[str, str]] = {
    ("/", "GET"): {
        "summary": "Redirect to CoreUI",
        "description": "Redirects the bare HTTP root to the CoreUI application shell at /webui.",
    },
    ("/health", "GET"): {
        "summary": "Check ChironAI stack health",
        "description": "Returns aggregate health for the local proxy host and required runtime services.",
    },
    ("/ready", "GET"): {
        "summary": "Readiness probe for ChironAI stack",
        "description": "Returns readiness for required runtime dependencies (Ollama provider and Qdrant).",
    },
    ("/metrics", "GET"): {
        "summary": "Export Prometheus metrics",
        "description": "Returns Prometheus text exposition for HTTP request counts, latency, and observability gauges.",
    },
    ("/api/webui/version", "GET"): {
        "summary": "Get application version",
        "description": "Returns the canonical ChironAI version, release stage, display name, and latest changelog entry used by CoreUI startup.",
    },
    ("/api/webui/help", "GET"): {
        "summary": "List help articles",
        "description": "Returns the in-app help knowledge base index (slug, title, tags) for CoreUI Help.",
    },
    ("/api/webui/help/{slug}", "GET"): {
        "summary": "Get help article",
        "description": "Returns one bundled markdown help article by slug.",
    },
    ("/api/webui/help/search", "GET"): {
        "summary": "Search help articles",
        "description": "Searches help titles, tags, and bodies. Query parameter ``q`` is required.",
    },
    ("/api/webui/sessions", "GET"): {
        "summary": "Create or resume CoreUI session",
        "description": "Returns a session id for browser-local CoreUI state. A supplied session_id query parameter is reused when valid.",
    },
    ("/api/webui/models", "GET"): {
        "summary": "List chat models",
        "description": "Returns provider-backed model rows available to CoreUI model pickers.",
    },
    ("/api/webui/config", "GET"): {
        "summary": "Get frontend runtime config",
        "description": "Returns lightweight configuration values needed by the CoreUI shell.",
    },
    ("/api/webui/chat", "POST"): {
        "summary": "Run WebUI chat request",
        "description": "Sends a CoreUI chat/test request through the configured provider and RAG proxy path.",
    },
    ("/api/webui/settings", "GET"): {
        "summary": "Get app settings",
        "description": "Returns persisted WebUI application settings plus active server port metadata.",
    },
    ("/api/webui/settings", "POST"): {
        "summary": "Update app settings",
        "description": "Persists WebUI application settings. The response includes effective port metadata and restart hints.",
    },
    ("/api/webui/model-settings", "GET"): {
        "summary": "Get proxy model settings",
        "description": "Returns the persisted RAG/proxy settings used by the model tester and chat surfaces.",
    },
    ("/api/webui/model-settings", "POST"): {
        "summary": "Update proxy model settings",
        "description": "Merges submitted fields into the stored proxy settings blob and returns the effective settings.",
    },
    ("/api/webui/prompts", "GET"): {
        "summary": "List prompt templates",
        "description": "Returns saved prompt template names and ids for CoreUI prompt selectors.",
    },
    ("/api/webui/prompts", "POST"): {
        "summary": "Create prompt template",
        "description": "Creates a new prompt template from submitted name/content fields.",
    },
    ("/api/webui/prompts/{name}", "GET"): {
        "summary": "Get prompt template",
        "description": "Returns the full content for a named prompt template.",
    },
    ("/api/webui/prompts/{name}", "PUT"): {
        "summary": "Update prompt template",
        "description": "Renames and/or updates the content for a named prompt template.",
    },
    ("/api/webui/prompts/{name}", "DELETE"): {
        "summary": "Delete prompt template",
        "description": "Moves a named prompt template to prompt trash.",
    },
    ("/api/webui/llm-proxy/status", "GET"): {
        "summary": "Get LLM proxy status",
        "description": "Returns the CoreUI status card payload for the local OpenAI-compatible LLM proxy.",
    },
    ("/api/webui/llm-proxy/builds", "GET"): {
        "summary": "List LLM proxy builds",
        "description": "Returns configured OpenAI-compatible model builds and diagnostic metadata for CoreUI.",
    },
    ("/api/webui/llm-proxy/builds", "PUT"): {
        "summary": "Replace LLM proxy builds",
        "description": "Validates and persists the submitted build list used by /v1 model routing.",
    },
    ("/api/webui/llm-proxy/builds/{build_id}", "GET"): {
        "summary": "Get LLM proxy build",
        "description": "Returns one configured proxy build by id, including diagnostics when available.",
    },
    ("/api/webui/llm-proxy/builds/preview-model", "POST"): {
        "summary": "Preview upstream model",
        "description": "Returns provider metadata for a model before saving it into an LLM proxy build.",
    },
    ("/api/webui/extensions/registry", "GET"): {
        "summary": "List registry extensions",
        "description": "Returns installable extension cards from the configured registry, including publisher and capability metadata.",
    },
    ("/api/webui/extensions/installed", "GET"): {
        "summary": "List installed extensions",
        "description": "Returns locally installed extensions, runtime status, security status, and optional Docker update metadata.",
    },
    ("/api/webui/extensions/providers", "GET"): {
        "summary": "List extension providers",
        "description": "Returns provider descriptors contributed by installed extensions.",
    },
    ("/api/webui/providers/catalog", "GET"): {
        "summary": "Get provider catalog",
        "description": "Returns all available LLM providers and model descriptors for CoreUI pickers.",
    },
    ("/api/webui/extensions/tabs", "GET"): {
        "summary": "List extension tabs",
        "description": "Returns extension-owned CoreUI tab descriptors, including iframe/declarative UI metadata and cached load state.",
    },
    ("/api/webui/extensions/{extension_id}/tab", "GET"): {
        "summary": "Get extension tab payload",
        "description": "Returns the render payload for one extension-owned tab.",
    },
    ("/api/webui/extensions/{extension_id}/tab/refresh", "POST"): {
        "summary": "Refresh extension tab payload",
        "description": "Starts or reuses a background refresh job for one extension tab payload.",
    },
    ("/api/webui/extensions/ui", "GET"): {
        "summary": "Get extension UI schemas",
        "description": "Returns declarative settings/status UI schemas contributed by installed extensions.",
    },
    ("/api/webui/extensions/{extension_id}/details", "GET"): {
        "summary": "Get extension details",
        "description": "Returns registry details, versions, README metadata, publisher metadata, and warnings for an extension.",
    },
    ("/api/webui/extensions/{extension_id}/actions/{action_id}", "POST"): {
        "summary": "Run extension action",
        "description": "Invokes an extension-owned action through the supported host runtime boundary.",
    },
    ("/api/webui/extensions/install", "POST"): {
        "summary": "Install extension",
        "description": "Installs an extension from the trusted registry metadata and returns lifecycle status.",
    },
    ("/api/webui/extensions/remove", "POST"): {
        "summary": "Remove extension",
        "description": "Removes an installed extension and reports whether backend restart is required.",
    },
    ("/api/webui/extensions/enable", "POST"): {
        "summary": "Enable extension",
        "description": "Enables an installed extension and refreshes extension runtime state.",
    },
    ("/api/webui/extensions/disable", "POST"): {
        "summary": "Disable extension",
        "description": "Disables an installed extension and refreshes extension runtime state.",
    },
    ("/api/webui/docker/status", "GET"): {
        "summary": "Get Docker status",
        "description": "Returns Docker availability and host diagnostics used by the Docker tab.",
    },
    ("/api/webui/docker/containers", "GET"): {
        "summary": "List Docker containers",
        "description": "Returns containers visible to the DockerManager host capability.",
    },
    ("/api/webui/docker/images", "GET"): {
        "summary": "List Docker images",
        "description": "Returns local Docker images visible to the DockerManager host capability.",
    },
    ("/api/webui/docker/events", "GET"): {
        "summary": "Stream Docker events",
        "description": "Server-sent event stream for Docker container and image changes.",
    },
    ("/api/webui/dependencies", "GET"): {
        "summary": "List project dependencies",
        "description": "Returns Python, npm, and Docker dependency inventory plus update capabilities.",
    },
    ("/api/webui/dependencies/check-updates", "POST"): {
        "summary": "Check dependency updates",
        "description": "Starts a dependency job that checks available package updates.",
    },
    ("/api/webui/dependencies/update", "POST"): {
        "summary": "Update dependencies",
        "description": "Starts a dependency job that applies supported dependency updates.",
    },
    ("/api/webui/dependencies/jobs/{job_id}", "GET"): {
        "summary": "Get dependency job",
        "description": "Returns live status, output, and result metadata for a dependency job.",
    },
    ("/api/webui/performance/startup", "GET"): {
        "summary": "Get startup performance",
        "description": "Returns backend startup phases and browser timing submitted by CoreUI.",
    },
    ("/api/webui/performance/browser-timing", "POST"): {
        "summary": "Submit browser timing",
        "description": "Stores browser Navigation Timing and CoreUI lifecycle measurements for the performance tab.",
    },
    ("/api/webui/rag/status", "GET"): {
        "summary": "Get RAG status",
        "description": "Returns Qdrant/RAG availability and collection status used by dashboard cards.",
    },
    ("/api/webui/rag/collections", "GET"): {
        "summary": "List RAG collections",
        "description": "Returns Qdrant collections and metadata for CoreUI collection selectors.",
    },
    ("/api/webui/rag/collections/{collection_name}", "DELETE"): {
        "summary": "Delete RAG collection",
        "description": "Deletes a named Qdrant collection after frontend confirmation.",
    },
    ("/api/webui/rag/start", "POST"): {
        "summary": "Start RAG service",
        "description": "Starts the local RAG/Qdrant service through the configured runtime boundary.",
    },
    ("/api/webui/rag/stop", "POST"): {
        "summary": "Stop RAG service",
        "description": "Stops the local RAG/Qdrant service through the configured runtime boundary.",
    },
    ("/api/webui/server/stop", "POST"): {
        "summary": "Stop WebUI backend server",
        "description": "Requests a graceful shutdown of the local WebUI backend process.",
    },
    ("/api/webui/notifications", "GET"): {
        "summary": "List CoreUI notifications",
        "description": "Returns persisted notification center entries for a browser session. Query parameter ``session_id`` is required.",
    },
    ("/api/webui/notifications", "POST"): {
        "summary": "Create CoreUI notification",
        "description": "Persists an error, event, or info notification for the CoreUI notification center.",
    },
    ("/api/webui/notifications/{nid}/dismiss", "PATCH"): {
        "summary": "Dismiss CoreUI notification",
        "description": "Marks a persisted notification as dismissed for the requesting session.",
    },
    ("/api/webui/notifications/clear", "POST"): {
        "summary": "Clear CoreUI notifications",
        "description": "Deletes all persisted notifications for a session. Live activity cards are unaffected.",
    },
    ("/api/webui/crawler/sources", "GET"): {
        "summary": "List crawler sources",
        "description": "Returns configured crawl sources with status metadata for CoreUI.",
    },
    ("/api/webui/crawler/sources", "POST"): {
        "summary": "Create crawler source",
        "description": "Registers a new crawl source from submitted configuration.",
    },
    ("/api/webui/crawler/sources/{source_id}", "GET"): {
        "summary": "Get crawler source",
        "description": "Returns one crawl source definition and runtime status.",
    },
    ("/api/webui/crawler/sources/{source_id}/crawl", "POST"): {
        "summary": "Start source crawl job",
        "description": "Starts or resumes crawling for the given source id.",
    },
    ("/api/webui/crawler/sources/{source_id}/crawl/status", "GET"): {
        "summary": "Get crawl job status",
        "description": "Returns progress and last error for an active or recent crawl job.",
    },
    ("/api/webui/crawler/create-collection", "POST"): {
        "summary": "Create collection from crawl",
        "description": "Starts background indexing that builds a Qdrant collection from crawled content.",
    },
    ("/v1", "GET"): {
        "summary": "Get OpenAI-compatible API root",
        "description": "Returns a lightweight marker for clients configured with the /v1 base URL.",
    },
    ("/v1", "POST"): {
        "summary": "Run chat completion from /v1 root",
        "description": "Compatibility endpoint for clients that POST chat-shaped payloads to the /v1 base URL.",
    },
    ("/v1/models", "GET"): {
        "summary": "List OpenAI-compatible models",
        "description": "Returns model objects exposed by configured LLM proxy builds.",
    },
    ("/v1/models/{model_id}", "GET"): {
        "summary": "Retrieve OpenAI-compatible model",
        "description": "Returns one model object, including compatibility capability aliases for IDE clients.",
    },
    ("/v1/chat/completions", "POST"): {
        "summary": "Create chat completion",
        "description": "OpenAI-compatible chat completions endpoint with ChironAI RAG/proxy extensions.",
    },
    ("/v1/responses", "POST"): {
        "summary": "Create response",
        "description": "OpenAI Responses compatibility endpoint mapped onto the ChironAI chat pipeline.",
    },
    ("/v1/messages", "POST"): {
        "summary": "Create Anthropic-compatible message",
        "description": "Anthropic Messages compatibility endpoint translated into the ChironAI chat pipeline.",
    },
}


def _fallback_summary(path: str, method: str) -> str:
    verb = {
        "GET": "Get",
        "POST": "Create",
        "PUT": "Update",
        "PATCH": "Patch",
        "DELETE": "Delete",
    }.get(method.upper(), method.title())
    tail = path.strip("/") or "root"
    if tail.startswith("api/webui/"):
        tail = tail[len("api/webui/") :]
    tail = re.sub(r"{([^}]+)}", r"\1", tail)
    words = re.sub(r"[-_/]+", " ", tail).strip()
    return f"{verb} {words}".strip()


def _operation_detail(path: str, method: str, endpoint: str) -> dict[str, str]:
    detail = dict(_OPERATION_DETAILS.get((path, method.upper()), {}))
    if "summary" not in detail:
        detail["summary"] = _fallback_summary(path, method)
    if "description" not in detail:
        detail["description"] = (
            f"Registered Flask endpoint `{endpoint}` for `{method.upper()} {path}`. "
            "Payload shape is currently described generically until the route is promoted into core contracts."
        )
    return detail


def _operation_id(endpoint: str, method: str) -> str:
    safe = re.sub(r"[^0-9a-zA-Z_]+", "_", endpoint).strip("_")
    return f"{safe}_{method.lower()}"


def _json_request_body(schema_ref: str = "#/components/schemas/GenericObject") -> dict[str, Any]:
    return {
        "required": False,
        "content": {
            "application/json": {
                "schema": {"$ref": schema_ref},
            }
        },
    }


def _json_response(schema_ref: str = "#/components/schemas/GenericObject", description: str = "OK") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": schema_ref},
            }
        },
    }


def _basic_responses(path: str, method: str) -> dict[str, Any]:
    method = method.upper()
    exact: dict[tuple[str, str], tuple[str, str]] = {
        ("/api/webui/version", "GET"): ("VersionResponse", "Current ChironAI version and latest changelog."),
        ("/api/webui/models", "GET"): ("ModelsListResponse", "Available provider models."),
        ("/api/webui/settings", "GET"): ("AppSettingsResponse", "Current WebUI settings."),
        ("/api/webui/settings", "POST"): ("AppSettingsResponse", "Updated WebUI settings."),
        ("/api/webui/model-settings", "GET"): ("ModelSettingsGetResponse", "Current proxy model settings."),
        ("/api/webui/model-settings", "POST"): ("ModelSettingsPostResponse", "Updated proxy model settings."),
        ("/api/webui/llm-proxy/status", "GET"): ("LlmProxyStatusResponse", "LLM proxy status."),
        ("/api/webui/llm-proxy/builds", "GET"): ("LlmProxyBuildsGetResponse", "Configured proxy builds."),
        ("/api/webui/llm-proxy/builds", "PUT"): ("LlmProxyBuildsPutOkResponse", "Updated proxy builds."),
        ("/api/webui/extensions/registry", "GET"): ("ExtensionRegistryResponse", "Extension registry cards."),
        ("/api/webui/extensions/installed", "GET"): ("InstalledExtensionsResponse", "Installed extensions."),
        ("/api/webui/extensions/tabs", "GET"): ("ExtensionTabsResponse", "Available extension tabs."),
        ("/api/webui/extensions/ui", "GET"): ("GenericObject", "Extension UI schema payload."),
        ("/api/webui/providers/catalog", "GET"): ("GenericObject", "Provider catalog."),
        ("/api/webui/docker/status", "GET"): ("DockerStatusResponse", "Docker runtime status."),
        ("/api/webui/docker/containers", "GET"): ("DockerListResponse", "Docker containers."),
        ("/api/webui/docker/images", "GET"): ("DockerListResponse", "Docker images."),
        ("/api/webui/dependencies", "GET"): ("DependenciesResponse", "Dependency inventory."),
        ("/api/webui/dependencies/jobs/{job_id}", "GET"): ("DependencyJobResponse", "Dependency job status."),
        ("/api/webui/performance/startup", "GET"): ("StartupPerformanceResponse", "Startup timing report."),
        ("/api/webui/rag/status", "GET"): ("RagStatusResponse", "RAG service status."),
        ("/api/webui/rag/collections", "GET"): ("RagCollectionsResponse", "RAG collections."),
        ("/api/webui/notifications", "GET"): ("NotificationsListResponse", "CoreUI notification list."),
        ("/api/webui/notifications", "POST"): ("NotificationCreateResponse", "Created notification id."),
        ("/api/webui/notifications/{nid}/dismiss", "PATCH"): ("NotificationDismissResponse", "Dismiss acknowledgement."),
        ("/api/webui/notifications/clear", "POST"): ("NotificationsClearResponse", "Clear result."),
        ("/v1", "GET"): ("GenericObject", "OpenAI-compatible API root."),
        ("/v1/models", "GET"): ("OpenAiModelListResponse", "OpenAI-compatible model list."),
        ("/v1/models/{model_id}", "GET"): ("OpenAiModelResponse", "OpenAI-compatible model metadata."),
        ("/v1/chat/completions", "POST"): ("OpenAiChatCompletionResponse", "OpenAI-compatible chat completion."),
        ("/v1/messages", "POST"): ("GenericObject", "Anthropic-compatible messages endpoint."),
        ("/v1/responses", "POST"): ("GenericObject", "OpenAI-compatible responses endpoint."),
        ("/v1/files/apply-edit", "POST"): ("GenericObject", "Apply file edit request."),
        ("/v1/external-docs/ingest", "POST"): ("GenericObject", "External documentation ingestion."),
    }
    schema, description = exact.get((path, method), ("GenericObject", "OK"))
    responses = {"200": _json_response(f"#/components/schemas/{schema}", description)}
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        responses.setdefault("400", _json_response("#/components/schemas/ErrorResponse", "Bad request"))
    return responses


def _request_body_for(path: str, method: str) -> dict[str, Any] | None:
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    exact: dict[tuple[str, str], str] = {
        ("/v1/chat/completions", "POST"): "#/components/schemas/OpenAiChatCompletionRequest",
        ("/api/webui/model-settings", "POST"): "#/components/schemas/GenericObject",
        ("/api/webui/settings", "POST"): "#/components/schemas/GenericObject",
        ("/api/webui/llm-proxy/builds", "PUT"): "#/components/schemas/GenericObject",
        ("/api/webui/performance/browser-timing", "POST"): "#/components/schemas/GenericObject",
        ("/api/webui/notifications", "POST"): "#/components/schemas/NotificationCreateRequest",
        ("/api/webui/notifications/{nid}/dismiss", "PATCH"): "#/components/schemas/NotificationDismissRequest",
        ("/api/webui/notifications/clear", "POST"): "#/components/schemas/NotificationsClearRequest",
    }
    return _json_request_body(exact.get((path, method), "#/components/schemas/GenericObject"))


def _components() -> dict[str, Any]:
    return {
        "schemas": {
            "GenericObject": {"type": "object", "additionalProperties": True},
            "ErrorResponse": {
                "type": "object",
                "properties": {"error": {"oneOf": [{"type": "string"}, {"type": "object"}]}},
                "additionalProperties": True,
            },
            "CoreUiNotification": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "session_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["error", "event", "info"]},
                    "source": {"type": "string"},
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "metadata": {"type": "object", "additionalProperties": True, "nullable": True},
                    "aggregation_key": {"type": "string", "nullable": True},
                    "occurrence_count": {"type": "integer"},
                    "is_console_error": {"type": "integer"},
                    "created_at": {"type": "string"},
                    "last_occurrence_at": {"type": "string", "nullable": True},
                    "dismissed_at": {"type": "string", "nullable": True},
                },
            },
            "NotificationsListResponse": {
                "type": "object",
                "required": ["notifications"],
                "properties": {
                    "notifications": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/CoreUiNotification"},
                    },
                },
            },
            "NotificationCreateRequest": {
                "type": "object",
                "required": ["session_id", "source", "title"],
                "properties": {
                    "session_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["error", "event", "info"]},
                    "source": {"type": "string"},
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "metadata": {"type": "object", "additionalProperties": True},
                    "aggregation_key": {"type": "string"},
                },
            },
            "NotificationCreateResponse": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
            "NotificationDismissRequest": {
                "type": "object",
                "required": ["session_id"],
                "properties": {"session_id": {"type": "string"}},
            },
            "NotificationDismissResponse": {
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
            "NotificationsClearRequest": {
                "type": "object",
                "required": ["session_id"],
                "properties": {"session_id": {"type": "string"}},
            },
            "NotificationsClearResponse": {
                "type": "object",
                "required": ["deleted"],
                "properties": {"deleted": {"type": "integer"}},
            },
            "VersionResponse": {
                "type": "object",
                "required": ["version", "app_name", "stage", "display_name"],
                "properties": {
                    "version": {"type": "string"},
                    "app_name": {"type": "string"},
                    "stage": {"type": "string"},
                    "changelog": {"type": "string"},
                    "display_name": {"type": "string"},
                    "error": {"type": "string"},
                },
            },
            "ModelsListResponse": {
                "type": "object",
                "required": ["models"],
                "properties": {
                    "models": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ProviderModelEntry"},
                    }
                },
            },
            "ProviderModelEntry": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "size": {"type": "integer"},
                    "modified_at": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "AppSettingsResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "rag_collection": {"type": "string"},
                    "server_port": {"type": "integer"},
                    "server_port_active": {"type": "integer"},
                    "server_port_source": {"type": "string"},
                    "server_port_restart_required": {"type": "boolean"},
                    "developer_mode": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            "ModelSettingsGetResponse": {"type": "object", "additionalProperties": True},
            "ModelSettingsPostResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "settings": {"type": "object", "additionalProperties": True},
                },
            },
            "LlmProxyStatusResponse": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "base_url": {"type": "string"},
                    "health": {"type": "string"},
                },
            },
            "LlmProxyBuildRow": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "swift-coder"},
                    "label": {"type": "string", "example": "Swift Coder"},
                    "backend": {"type": "string", "example": "ollama"},
                    "model": {"type": "string", "example": "qwen2.5-coder:7b"},
                    "prompt_name": {"type": "string", "example": "default"},
                    "use_prompt_template": {"type": "boolean"},
                    "healthy": {"type": "boolean"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
            "LlmProxyBuildsGetResponse": {
                "type": "object",
                "properties": {
                    "builds": {"type": "array", "items": {"$ref": "#/components/schemas/LlmProxyBuildRow"}},
                    "openai_models_urls": {
                        "type": "object",
                        "properties": {"main": {"type": "string", "example": "http://127.0.0.1:8080/v1/models"}},
                    },
                },
            },
            "LlmProxyBuildsPutOkResponse": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean", "example": True},
                    "builds": {"type": "array", "items": {"$ref": "#/components/schemas/LlmProxyBuildRow"}},
                },
            },
            "ExtensionCapability": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "iframe_tab"},
                    "label": {"type": "string", "example": "Iframe tab"},
                    "description": {"type": "string"},
                    "risk": {"type": "string", "example": "low"},
                    "requires_user_consent": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            "ExtensionCard": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "open-webui"},
                    "title": {"type": "string", "example": "Open WebUI"},
                    "description": {"type": "string"},
                    "icon": {"type": "string"},
                    "latest_version": {"type": "string", "example": "0.1.0"},
                    "repository": {"type": "string"},
                    "repository_id": {"type": "string"},
                    "visibility": {"type": "string", "example": "trusted"},
                    "publisher": {"type": "object", "additionalProperties": True},
                    "capabilities": {"type": "array", "items": {"$ref": "#/components/schemas/ExtensionCapability"}},
                    "blocklist": {"type": "object", "additionalProperties": True},
                },
                "additionalProperties": True,
            },
            "ExtensionRegistryResponse": {
                "type": "object",
                "properties": {
                    "entries": {"type": "array", "items": {"$ref": "#/components/schemas/ExtensionCard"}},
                    "registry_url": {"type": "string"},
                    "cache_age_sec": {"type": "integer"},
                },
                "additionalProperties": True,
            },
            "ExtensionDockerStatus": {
                "type": "object",
                "properties": {
                    "container_name": {"type": "string", "example": "open-webui"},
                    "image": {"type": "string"},
                    "running": {"type": "boolean"},
                    "data_persisted": {"type": "boolean"},
                    "update_available": {"type": "boolean"},
                    "update_status": {"type": "string"},
                    "current_version": {"type": "string"},
                    "update_version": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "InstalledExtension": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "ollama-provider"},
                    "version": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "installed": {"type": "boolean"},
                    "restart_required": {"type": "boolean"},
                    "status": {"type": "string", "example": "ready"},
                    "error": {"type": "string"},
                    "security_blocked": {"type": "boolean"},
                    "sandboxed": {"type": "boolean"},
                    "sandbox_status": {"type": "string"},
                    "docker": {"$ref": "#/components/schemas/ExtensionDockerStatus"},
                },
                "additionalProperties": True,
            },
            "InstalledExtensionsResponse": {
                "type": "object",
                "properties": {
                    "extensions": {"type": "array", "items": {"$ref": "#/components/schemas/InstalledExtension"}}
                },
                "additionalProperties": True,
            },
            "ExtensionTabLoadState": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "ready"},
                    "phases": {"type": "object", "additionalProperties": {"type": "string"}},
                    "job_id": {"type": "string"},
                    "started_at": {"type": "string"},
                    "finished_at": {"type": "string"},
                    "duration_ms": {"type": "number", "nullable": True},
                    "cached_at": {"type": "string"},
                    "error": {"type": "string"},
                },
            },
            "ExtensionTab": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "open-webui"},
                    "extension_id": {"type": "string", "example": "open-webui"},
                    "title": {"type": "string", "example": "Open WebUI"},
                    "icon": {"type": "string"},
                    "icon_url": {"type": "string"},
                    "description": {"type": "string"},
                    "frame": {"type": "object", "additionalProperties": True},
                    "order": {"type": "integer"},
                    "status": {"type": "object", "nullable": True, "additionalProperties": True},
                    "load_state": {"$ref": "#/components/schemas/ExtensionTabLoadState"},
                },
                "additionalProperties": True,
            },
            "ExtensionTabsResponse": {
                "type": "object",
                "properties": {
                    "available": {"type": "boolean", "example": True},
                    "runtime_status": {"type": "string", "example": "ready"},
                    "tabs": {"type": "array", "items": {"$ref": "#/components/schemas/ExtensionTab"}},
                },
            },
            "DockerStatusResponse": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "available": {"type": "boolean"},
                    "running": {"type": "boolean"},
                    "version": {"type": "string"},
                    "error": {"type": "string"},
                    "details": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "DockerListResponse": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "items": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "containers": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "images": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "error": {"type": "string"},
                    "details": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "DependencySource": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "group": {"type": "string"},
                    "requested": {"type": "string"},
                },
            },
            "Dependency": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "python:flask"},
                    "ecosystem": {"type": "string", "example": "python"},
                    "name": {"type": "string", "example": "flask"},
                    "requested": {"type": "string"},
                    "installed_version": {"type": "string", "nullable": True},
                    "latest_version": {"type": "string", "nullable": True},
                    "status": {"type": "string", "example": "installed"},
                    "manager": {"type": "string"},
                    "sources": {"type": "array", "items": {"$ref": "#/components/schemas/DependencySource"}},
                },
            },
            "DependenciesResponse": {
                "type": "object",
                "properties": {
                    "dependencies": {"type": "array", "items": {"$ref": "#/components/schemas/Dependency"}},
                    "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "generated_at": {"type": "string"},
                    "update_capabilities": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                },
            },
            "DependencyJobResponse": {
                "type": "object",
                "properties": {"job": {"type": "object", "additionalProperties": True}},
            },
            "StartupPerformanceResponse": {
                "type": "object",
                "properties": {
                    "server_start_epoch_ms": {"type": "number"},
                    "total_duration_ms": {"type": "number"},
                    "phases": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "browser_timing": {"type": "object", "additionalProperties": True},
                },
            },
            "RagStatusResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "ok"},
                    "qdrant": {"type": "object", "additionalProperties": True},
                    "collections": {"type": "array", "items": {"type": "string"}},
                    "error": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "RagCollectionsResponse": {
                "type": "object",
                "properties": {
                    "collections": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "active_collection": {"type": "string"},
                    "error": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "OpenAiModelListResponse": {
                "type": "object",
                "properties": {
                    "object": {"type": "string"},
                    "data": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/OpenAiModelResponse"},
                    },
                },
            },
            "OpenAiModelResponse": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "swift-coder"},
                    "object": {"type": "string", "example": "model"},
                    "created": {"type": "integer"},
                    "owned_by": {"type": "string", "example": "chironai"},
                    "supports_vision": {"type": "boolean"},
                    "supports_tools": {"type": "boolean"},
                    "modalities": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object", "additionalProperties": True},
                },
                "additionalProperties": True,
            },
            "OpenAiChatCompletionRequest": {
                "type": "object",
                "required": ["messages"],
                "properties": {
                    "model": {"type": "string"},
                    "messages": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "stream": {"type": "boolean"},
                    "temperature": {"type": "number"},
                    "tools": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "tool_choice": {
                        "oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}],
                    },
                },
                "additionalProperties": True,
            },
            "OpenAiChatCompletionResponse": {"type": "object", "additionalProperties": True},
        }
    }


def build_openapi_spec(app: Flask) -> dict[str, Any]:
    """Build an OpenAPI document from the registered Flask route map."""
    paths: dict[str, Any] = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        endpoint = str(rule.endpoint or "")
        if endpoint.split(".")[-1] in _INTERNAL_ENDPOINT_SUFFIXES:
            continue
        path = _openapi_path(rule.rule)
        methods = sorted(method for method in (rule.methods or ()) if method not in {"HEAD", "OPTIONS"})
        if not methods:
            continue
        path_item = paths.setdefault(path, {})
        for method in methods:
            detail = _operation_detail(path, method, endpoint)
            operation = {
                "tags": [_tag_for_path(path)],
                "operationId": _operation_id(endpoint, method),
                "summary": detail["summary"],
                "description": detail["description"],
                "parameters": _path_parameters(rule.rule),
                "responses": _basic_responses(path, method),
                "x-flask-endpoint": endpoint,
            }
            request_body = _request_body_for(path, method)
            if request_body is not None:
                operation["requestBody"] = request_body
            path_item[method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": f"{APP_NAME} API",
            "version": VERSION,
            "description": f"{APP_NAME} {APP_STAGE} OpenAPI description generated from Flask routes.",
        },
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": _components(),
    }


def build_swagger_ui_spec(app: Flask) -> dict[str, Any]:
    """Build the OpenAPI document variant accepted by the bundled Swagger UI."""
    spec = deepcopy(build_openapi_spec(app))
    spec["openapi"] = "3.0.3"
    spec.pop("jsonSchemaDialect", None)
    _normalize_json_schema_keywords(spec)
    return spec


def _normalize_json_schema_keywords(value: Any) -> None:
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        mapping.pop("$schema", None)
        if "const" in mapping and "enum" not in mapping:
            mapping["enum"] = [mapping.pop("const")]
        else:
            mapping.pop("const", None)
        for child in mapping.values():
            _normalize_json_schema_keywords(child)
    elif isinstance(value, list):
        for child in cast(list[Any], value):
            _normalize_json_schema_keywords(child)


_SWAGGER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChironAI Swagger</title>
  <link rel="stylesheet" href="{{ asset_base }}/swagger-ui.css" />
  <style>
    body { margin: 0; background: #ffffff; }
    #swagger-ui { min-height: 100vh; }
    .topbar { display: none; }
    .swagger-ui .scheme-container { box-shadow: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{{ asset_base }}/swagger-ui-bundle.js"></script>
  <script src="{{ asset_base }}/swagger-ui-standalone-preset.js"></script>
  <script>
    window.addEventListener("load", function () {
      window.ui = SwaggerUIBundle({
        url: "{{ spec_url }}",
        dom_id: "#swagger-ui",
        deepLinking: true,
        persistAuthorization: true,
        displayRequestDuration: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ]
      });
    });
  </script>
</body>
</html>
"""


def register_openapi_routes(app: Flask, *, url_prefix: str = WEBUI_URL_PREFIX) -> None:
    """Register stable OpenAPI JSON and Swagger UI endpoints for an app."""

    spec_path = f"{url_prefix.rstrip('/')}/openapi.json"
    swagger_path = f"{url_prefix.rstrip('/')}/swagger/"
    swagger_spec_path = f"{url_prefix.rstrip('/')}/swagger/openapi.json"
    asset_path = f"{url_prefix.rstrip('/')}/swagger-assets/<path:filename>"
    asset_base = f"{url_prefix.rstrip('/')}/swagger-assets"

    @app.get(spec_path, endpoint="openapi_json")
    def openapi_json() -> Any:
        return jsonify(build_openapi_spec(current_app))

    @app.get(swagger_spec_path, endpoint="swagger_openapi_json")
    def swagger_openapi_json() -> Any:
        return jsonify(build_swagger_ui_spec(current_app))

    @app.get(swagger_path, endpoint="swagger_ui")
    def swagger_ui() -> Response:
        html = render_template_string(_SWAGGER_HTML, spec_url=swagger_spec_path, asset_base=asset_base)
        return Response(html, mimetype="text/html; charset=utf-8")

    @app.get(asset_path, endpoint="swagger_asset")
    def swagger_asset(filename: str) -> Response:
        if "\\" in filename or any(part in {"", ".", ".."} for part in filename.split("/")):
            abort(404)
        try:
            static_root = resources.files("flask_restx").joinpath("static")
            target = static_root.joinpath(filename)
            if not target.is_file():
                abort(404)
            return send_file(str(target))
        except ModuleNotFoundError:
            abort(503, description="flask-restx is not installed")


__all__ = ["build_openapi_spec", "build_swagger_ui_spec", "register_openapi_routes"]
