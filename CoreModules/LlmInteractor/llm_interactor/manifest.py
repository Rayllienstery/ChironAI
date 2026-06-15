"""Extension manifests and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EXTENSION_API_VERSION = "1"
EXTENSION_TYPE_LLM_PROVIDER = "llm_provider"
EXTENSION_TYPE_UI_EXTENSION = "ui_extension"
SUPPORTED_EXTENSION_TYPES = {EXTENSION_TYPE_LLM_PROVIDER, EXTENSION_TYPE_UI_EXTENSION}
ALLOWED_UI_COMPONENT_TYPES = {
    "page",
    "section",
    "text",
    "badge",
    "status",
    "input",
    "select",
    "switch",
    "secret",
    "action",
    "button",
    "table",
    "list",
    "diagnostics",
}


@dataclass(frozen=True)
class BackendManifest:
    entrypoint: str


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    version: str
    api_version: str
    type: str
    title: str
    description: str = ""
    icon: str = ""
    backend: BackendManifest | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    compatibility: dict[str, Any] = field(default_factory=dict)
    settings_schema: dict[str, Any] = field(default_factory=dict)
    ui_schema: dict[str, Any] = field(default_factory=dict)
    models_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _validate_ui_schema(schema: Any) -> None:
    if not isinstance(schema, dict):
        raise ValueError("ui_schema must be an object")
    pages = schema.get("pages")
    if pages is None:
        return
    if not isinstance(pages, list):
        raise ValueError("ui_schema.pages must be a list")
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("ui_schema.pages items must be objects")
        sections = page.get("sections", [])
        if not isinstance(sections, list):
            raise ValueError("ui_schema page sections must be a list")
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError("ui_schema section must be an object")
            components = section.get("components", [])
            if not isinstance(components, list):
                raise ValueError("ui_schema section components must be a list")
            for comp in components:
                if not isinstance(comp, dict):
                    raise ValueError("ui_schema component must be an object")
                ctype = str(comp.get("type") or "").strip().lower()
                if ctype not in ALLOWED_UI_COMPONENT_TYPES:
                    raise ValueError(f"unsupported ui_schema component type: {ctype}")


def manifest_from_dict(raw: dict[str, Any]) -> ExtensionManifest:
    if not isinstance(raw, dict):
        raise ValueError("manifest must be an object")
    ext_id = str(raw.get("id") or "").strip()
    version = str(raw.get("version") or "").strip()
    api_version = str(raw.get("api_version") or "").strip()
    ext_type = str(raw.get("type") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not ext_id:
        raise ValueError("manifest.id is required")
    if not version:
        raise ValueError("manifest.version is required")
    if api_version != EXTENSION_API_VERSION:
        raise ValueError(f"unsupported manifest api_version: {api_version}")
    if ext_type not in SUPPORTED_EXTENSION_TYPES:
        raise ValueError(f"unsupported manifest type: {ext_type}")
    if not title:
        raise ValueError("manifest.title is required")
    backend_raw = raw.get("backend")
    backend = None
    if isinstance(backend_raw, dict):
        entrypoint = str(backend_raw.get("entrypoint") or "").strip()
        if not entrypoint:
            raise ValueError("manifest.backend.entrypoint is required")
        backend = BackendManifest(entrypoint=entrypoint)
    else:
        raise ValueError("manifest.backend is required")
    settings_schema = raw.get("settings_schema")
    if settings_schema is None:
        settings_schema = {}
    ui_schema = raw.get("ui_schema")
    if ui_schema is None:
        ui_schema = {}
    _validate_ui_schema(ui_schema)
    return ExtensionManifest(
        id=ext_id,
        version=version,
        api_version=api_version,
        type=ext_type,
        title=title,
        description=str(raw.get("description") or ""),
        icon=str(raw.get("icon") or ""),
        backend=backend,
        capabilities=dict(raw.get("capabilities") or {}),
        compatibility=dict(raw.get("compatibility") or {}),
        settings_schema=dict(settings_schema or {}),
        ui_schema=dict(ui_schema or {}),
        models_policy=dict(raw.get("models_policy") or {}),
        metadata={k: v for k, v in raw.items() if k not in {
            "id",
            "version",
            "api_version",
            "type",
            "title",
            "description",
            "icon",
            "backend",
            "capabilities",
            "compatibility",
            "settings_schema",
            "ui_schema",
            "models_policy",
        }},
    )
