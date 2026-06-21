"""Pure helpers for extension install validation and provenance."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable

from llm_interactor.install_state import InstalledExtensionRecord
from llm_interactor.manifest import EXTENSION_API_VERSION

_log = logging.getLogger(__name__)

_SEMVERISH_RE = re.compile(r"^v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")

_HIGH_RISK_CAPABILITIES = {
    "docker",
    "docker_runtime",
    "host_services",
    "service_actions",
    "settings",
    "secrets",
    "network",
    "filesystem",
    "shell",
    "subprocess",
    "native_process",
    "iframe_tab",
    "external_urls",
    "model_delete",
}

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def enabled_capability_ids(capabilities: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key, value in dict(capabilities or {}).items():
        cap = str(key or "").strip()
        if not cap:
            continue
        enabled = bool(value.get("enabled", True)) if isinstance(value, dict) else bool(value)
        if enabled:
            out.add(cap)
    return out


def capability_expansion(
    existing: InstalledExtensionRecord | None,
    next_capabilities: dict[str, Any],
    *,
    installed_capabilities_fn: Callable[[InstalledExtensionRecord], dict[str, Any]],
) -> list[dict[str, Any]]:
    if existing is None:
        return []
    previous = installed_capabilities_fn(existing)
    previous_ids = enabled_capability_ids(previous)
    next_ids = enabled_capability_ids(next_capabilities)
    added = sorted(next_ids - previous_ids)
    return [
        {
            "id": cap,
            "label": cap.replace("_", " ").title(),
            "risk": "high" if cap in _HIGH_RISK_CAPABILITIES else "medium",
            "requires_user_consent": cap in _HIGH_RISK_CAPABILITIES,
        }
        for cap in added
    ]


def validate_compatibility(compatibility: dict[str, Any]) -> None:
    api_version = str(compatibility.get("extension_api_version") or EXTENSION_API_VERSION).strip()
    if api_version != EXTENSION_API_VERSION:
        raise ValueError(f"unsupported extension_api_version: {api_version}")
    app = str(compatibility.get("app") or "chironai").strip().lower()
    if app not in {"chironai", "chiron ai"}:
        raise ValueError(f"unsupported extension app compatibility: {app}")


def validate_install_manifest(entry: dict[str, Any], manifest: Any, target_version: str) -> None:
    expected_id = str(entry.get("id") or "").strip()
    if manifest.id != expected_id:
        raise ValueError(f"manifest id mismatch: expected '{expected_id}', got '{manifest.id}'")
    if _SEMVERISH_RE.match(target_version):
        if manifest.version.lstrip("v") != target_version.lstrip("v"):
            raise ValueError(f"manifest version mismatch: expected '{target_version}', got '{manifest.version}'")
    else:
        if not str(manifest.version or "").strip():
            raise ValueError(
                f"manifest for extension '{expected_id}' installed from ref '{target_version}' "
                "must declare a non-empty version"
            )
    validate_compatibility(dict(getattr(manifest, "compatibility", {}) or {}))
    registry_compat = entry.get("compatibility")
    if isinstance(registry_compat, dict):
        validate_compatibility(dict(registry_compat))
    expected_sha = str(entry.get("manifest_sha256") or "").strip().lower()
    if expected_sha:
        if not _SHA256_RE.match(expected_sha):
            raise ValueError("registry manifest_sha256 must be a 64-character sha256 hex digest")
        actual_sha = str(getattr(manifest, "manifest_sha256", "") or "").strip().lower()
        if actual_sha and actual_sha != expected_sha:
            raise ValueError(f"manifest_sha256 mismatch: expected '{expected_sha}', got '{actual_sha}'")


def entry_with_version_payload(entry: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    archive_url = str(version.get("archive_url") or "").strip()
    if archive_url:
        out["archive_url"] = archive_url
    for key in ("digest", "commit_sha", "provenance_level", "release_url", "target_kind"):
        if version.get(key):
            out[key] = version[key]
    return out


def install_provenance(
    entry: dict[str, Any],
    selected_ref: str,
    *,
    storage_version: str,
) -> dict[str, Any]:
    repository = str(entry.get("repository") or entry.get("repo_url") or "").strip()
    archive_url = str(entry.get("archive_url") or "").strip()
    source_path = str(entry.get("source_path") or "").strip()
    provenance_level = str(
        entry.get("provenance_level")
        or ("local_source" if source_path else "github_release_asset" if archive_url else "unknown")
    )
    return {
        "repository": repository,
        "repository_id": str(entry.get("repository_id") or ""),
        "selected_ref": selected_ref,
        "selected_version": selected_ref,
        "storage_version": storage_version,
        "target_kind": str(entry.get("target_kind") or ("release" if _SEMVERISH_RE.match(selected_ref) else "branch")),
        "resolved_commit_sha": str(entry.get("resolved_commit_sha") or entry.get("commit_sha") or ""),
        "archive_url": archive_url,
        "digest": str(entry.get("digest") or ""),
        "provenance_level": provenance_level,
        "source_path": source_path,
        "installed_at": utc_now_iso(),
    }


def resolve_install_target(
    entry: dict[str, Any],
    requested_ref: str,
    *,
    repository_client: Any | None,
) -> tuple[dict[str, Any], str]:
    resolved = dict(entry)
    repository = str(resolved.get("repository") or resolved.get("repo_url") or "").strip()
    if not repository or repository_client is None:
        return resolved, requested_ref
    if requested_ref:
        try:
            for version in repository_client.releases(repository):
                ref = str(version.get("ref") or version.get("version") or "").strip()
                if ref == requested_ref or ref.lstrip("v") == requested_ref.lstrip("v"):
                    return entry_with_version_payload(resolved, version), ref
        except Exception as exc:
            _log.warning(
                "extension install: could not fetch releases for %s (ref=%s): %s: %s",
                repository,
                requested_ref,
                type(exc).__name__,
                exc,
            )
        return resolved, requested_ref
    latest = repository_client.latest_release(repository)
    latest_ref = str(latest.get("ref") or latest.get("version") or "").strip()
    return entry_with_version_payload(resolved, latest), latest_ref
