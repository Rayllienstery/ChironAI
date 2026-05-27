"""Extension management HTTP/API contract.

This module is intentionally implementation-free. It defines the target DTOs and
route constants shared by CoreUI/WebUIBackend, the future ``extensions_backend``
module, and the extension host/runtime layer.

Ownership boundary:
- ``modules/extensions_backend`` owns registry polling, GitHub repository
  metadata, install/update/remove, blocklist policy, local install state, and
  lifecycle status.
- Core modules expose host/runtime/sandbox capability surfaces only.
- CoreUI, WebUIBackend, and LlmProxy consume extension state through contracts.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


EXTENSIONS_API_VERSION: str = "1"
EXTENSIONS_API_PREFIX: str = "/api/extensions"
WEBUI_EXTENSIONS_PROXY_PREFIX: str = "/api/webui/extensions"


ExtensionType = Literal["llm_provider", "ui_extension"]
ExtensionVisibility = Literal["official", "trusted", "community", "experimental", "blocked"]
PublisherTrustState = Literal["official", "trusted", "community", "experimental", "blocked", "unknown"]
InstallTargetKind = Literal["latest_release", "release", "tag", "branch", "commit"]
ProvenanceLevel = Literal[
    "attested_release_asset",
    "digest_release_asset",
    "github_release_asset",
    "github_tag_archive",
    "branch_or_commit_archive",
    "local_source",
    "unknown",
]
SecurityScanStatus = Literal["not_scanned", "passed", "warning", "blocked", "failed"]
ExtensionRuntimeState = Literal[
    "not_installed",
    "installed",
    "loading",
    "ready",
    "degraded",
    "failed",
    "blocked",
    "disabled",
    "removed",
]
ExtensionLifecycleOperation = Literal[
    "install",
    "update",
    "enable",
    "disable",
    "remove",
    "rollback",
    "purge_data",
    "restart",
    "kill",
]
RestartScope = Literal["none", "extension", "provider_registry", "backend", "app"]


class ExtensionsErrorResponse(TypedDict, total=False):
    error: str
    code: str
    details: dict[str, Any]


class ExtensionCompatibilityDTO(TypedDict, total=False):
    extension_api_version: str
    app: str
    min_app_version: str
    max_app_version: str | None


class ExtensionCapabilityDTO(TypedDict, total=False):
    """Declared capability or permission shown before install/update."""

    id: str
    label: str
    description: str
    risk: Literal["low", "medium", "high", "critical"]
    requires_user_consent: bool


class ExtensionPublisherDTO(TypedDict, total=False):
    name: str
    url: str
    trust_state: PublisherTrustState
    verified: bool


class ExtensionRegistryEntryDTO(TypedDict, total=False):
    """One entry from the central registry.

    Version lists are intentionally absent. Available versions are resolved from
    the repository when the details modal/version dropdown is opened.
    """

    id: str
    title: str
    description: str
    icon: str
    repository: str
    repository_id: str
    homepage: str
    license: str
    publisher: str
    publisher_url: str
    visibility: ExtensionVisibility
    tags: list[str]
    compatibility: ExtensionCompatibilityDTO
    capabilities: list[ExtensionCapabilityDTO]


class ExtensionRegistryResponse(TypedDict):
    registry_url: str
    cache_age_sec: int
    entries: list[ExtensionRegistryEntryDTO]


class ExtensionVersionDTO(TypedDict, total=False):
    version: str
    ref: str
    target_kind: InstallTargetKind
    commit_sha: str
    release_url: str
    archive_url: str
    digest: str
    provenance_level: ProvenanceLevel
    published_at: str
    is_latest: bool
    is_prerelease: bool
    warnings: list[str]


class ExtensionVersionsResponse(TypedDict, total=False):
    extension_id: str
    repository: str
    cache_age_sec: int
    versions: list[ExtensionVersionDTO]
    latest: ExtensionVersionDTO
    error: str


class ExtensionReadmeResponse(TypedDict, total=False):
    extension_id: str
    repository: str
    ref: str
    commit_sha: str
    markdown: str
    sanitized_html: str
    cache_age_sec: int
    warnings: list[str]
    error: str


class ExtensionManifestPreviewDTO(TypedDict, total=False):
    id: str
    version: str
    api_version: str
    type: ExtensionType
    title: str
    description: str
    icon: str
    capabilities: dict[str, Any]
    settings_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    compatibility: ExtensionCompatibilityDTO
    high_risk_capabilities: list[ExtensionCapabilityDTO]
    capability_expansion: list[ExtensionCapabilityDTO]


class ExtensionDetailsResponse(TypedDict, total=False):
    entry: ExtensionRegistryEntryDTO
    versions: list[ExtensionVersionDTO]
    latest: ExtensionVersionDTO
    readme: ExtensionReadmeResponse
    manifest_preview: ExtensionManifestPreviewDTO
    publisher: ExtensionPublisherDTO


class ExtensionInstallTargetDTO(TypedDict, total=False):
    target_kind: InstallTargetKind
    version: str
    ref: str
    commit_sha: str
    archive_url: str


class ExtensionInstallRequest(TypedDict, total=False):
    extension_id: str
    target: ExtensionInstallTargetDTO
    accepted_capabilities: list[str]
    allow_weak_provenance: bool
    allow_capability_expansion: bool


class ExtensionProvenanceDTO(TypedDict, total=False):
    repository: str
    repository_id: str
    selected_ref: str
    selected_version: str
    target_kind: InstallTargetKind
    resolved_commit_sha: str
    archive_url: str
    digest: str
    provenance_level: ProvenanceLevel
    installed_at: str


class ExtensionSecurityFindingDTO(TypedDict, total=False):
    severity: Literal["info", "warning", "critical"]
    code: str
    file: str
    line: int
    message: str
    evidence: str


class ExtensionSecurityScanDTO(TypedDict, total=False):
    status: SecurityScanStatus
    scanned_at: str
    scanner_version: str
    findings: list[ExtensionSecurityFindingDTO]
    dependency_inventory: dict[str, Any]
    sbom_url: str


class ExtensionBlocklistMatchDTO(TypedDict, total=False):
    matched: bool
    reason: str
    source: str
    matched_on: Literal["extension_id", "version", "ref", "repository_id", "publisher"]


class InstalledExtensionDTO(TypedDict, total=False):
    id: str
    version: str
    enabled: bool
    installed: bool
    status: ExtensionRuntimeState
    title: str
    description: str
    icon: str
    provenance: ExtensionProvenanceDTO
    security_scan: ExtensionSecurityScanDTO
    blocklist: ExtensionBlocklistMatchDTO
    capabilities: list[ExtensionCapabilityDTO]
    restart_required: bool
    restart_scope: RestartScope
    error: str


class InstalledExtensionsResponse(TypedDict):
    extensions: list[InstalledExtensionDTO]


class ExtensionLifecycleRequest(TypedDict, total=False):
    extension_id: str
    operation: ExtensionLifecycleOperation
    target: ExtensionInstallTargetDTO
    purge_data: bool


class ExtensionLifecycleResponse(TypedDict, total=False):
    id: str
    operation: ExtensionLifecycleOperation
    status: ExtensionRuntimeState
    ok: bool
    restart_required: bool
    restart_scope: RestartScope
    runtime_generation: int
    previous_runtime_generation: int
    notification_id: int
    message: str
    error: str


class ExtensionRuntimeStatusDTO(TypedDict, total=False):
    id: str
    status: ExtensionRuntimeState
    runtime_generation: int
    sandboxed: bool
    sandbox_pid: int
    sandbox_status: str
    sandbox_error: str
    sandbox_restart_count: int
    sandbox_blocked: bool
    last_error: str


class ExtensionRuntimeStatusResponse(TypedDict):
    extensions: list[ExtensionRuntimeStatusDTO]


class ExtensionTabDTO(TypedDict, total=False):
    id: str
    extension_id: str
    title: str
    icon: str
    icon_url: str
    description: str
    frame: dict[str, Any]
    order: int
    status: dict[str, Any]


class ExtensionTabsResponse(TypedDict):
    tabs: list[ExtensionTabDTO]


class ExtensionProviderDTO(TypedDict, total=False):
    provider_id: str
    extension_id: str
    title: str
    description: str
    icon_url: str
    capabilities: dict[str, Any]
    health: dict[str, Any]
    models: list[dict[str, Any]]


class ExtensionProviderCatalogResponse(TypedDict):
    providers: list[ExtensionProviderDTO]
    models: list[dict[str, Any]]


def extensions_abs_path(suffix: str) -> str:
    """Return an extensions backend API path for a suffix such as ``/registry``."""
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    return f"{EXTENSIONS_API_PREFIX}{suffix}"


__all__ = [
    "EXTENSIONS_API_VERSION",
    "EXTENSIONS_API_PREFIX",
    "WEBUI_EXTENSIONS_PROXY_PREFIX",
    "ExtensionType",
    "ExtensionVisibility",
    "PublisherTrustState",
    "InstallTargetKind",
    "ProvenanceLevel",
    "SecurityScanStatus",
    "ExtensionRuntimeState",
    "ExtensionLifecycleOperation",
    "RestartScope",
    "ExtensionsErrorResponse",
    "ExtensionCompatibilityDTO",
    "ExtensionCapabilityDTO",
    "ExtensionPublisherDTO",
    "ExtensionRegistryEntryDTO",
    "ExtensionRegistryResponse",
    "ExtensionVersionDTO",
    "ExtensionVersionsResponse",
    "ExtensionReadmeResponse",
    "ExtensionManifestPreviewDTO",
    "ExtensionDetailsResponse",
    "ExtensionInstallTargetDTO",
    "ExtensionInstallRequest",
    "ExtensionProvenanceDTO",
    "ExtensionSecurityFindingDTO",
    "ExtensionSecurityScanDTO",
    "ExtensionBlocklistMatchDTO",
    "InstalledExtensionDTO",
    "InstalledExtensionsResponse",
    "ExtensionLifecycleRequest",
    "ExtensionLifecycleResponse",
    "ExtensionRuntimeStatusDTO",
    "ExtensionRuntimeStatusResponse",
    "ExtensionTabDTO",
    "ExtensionTabsResponse",
    "ExtensionProviderDTO",
    "ExtensionProviderCatalogResponse",
    "extensions_abs_path",
]
