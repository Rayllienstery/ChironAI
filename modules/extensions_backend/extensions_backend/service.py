"""Contract-facing extension-management service facade."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SAFE_EXTENSION_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,62}[A-Za-z0-9])?$")
_SAFE_ACTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _require_extension_id(extension_id: Any) -> str:
    value = str(extension_id or "").strip()
    if not value:
        raise ValueError("extension_id is required")
    if not _SAFE_EXTENSION_ID_RE.match(value):
        raise ValueError(
            f"extension_id {value!r} contains invalid characters; "
            "use only letters, digits, hyphens, and underscores (1–64 characters)"
        )
    return value


def _require_action_id(action_id: Any) -> str:
    value = str(action_id or "").strip()
    if not value:
        raise ValueError("action_id is required")
    if not _SAFE_ACTION_ID_RE.match(value):
        raise ValueError(f"action_id {value!r} contains invalid characters")
    return value


def _sanitize_install_target(target: Any) -> dict[str, Any] | None:
    """Validate and return a clean install target dict, or None."""
    if target is None:
        return None
    if not isinstance(target, dict):
        raise ValueError("install target must be a JSON object")
    out: dict[str, Any] = {}
    for key in ("target_kind", "version", "ref", "commit_sha", "archive_url"):
        value = target.get(key)
        if value is not None:
            out[key] = str(value)
    for key in ("allow_capability_expansion", "capability_expansion_accepted"):
        if key in target:
            out[key] = bool(target[key])
    return out or None


class ExtensionManagementService:
    """Expose extension operations without leaking manager internals to HTTP routes.

    This facade is the contract boundary between HTTP routes and the extension
    manager.  It validates all caller-supplied inputs before delegating to the
    manager, ensuring that no unsanitized data reaches the installation pipeline.
    """

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    @property
    def runtime(self) -> Any | None:
        return getattr(self._manager, "runtime", None)

    @property
    def registry(self) -> Any | None:
        return getattr(self._manager, "registry", None)

    @property
    def runtime_status(self) -> str:
        return str(getattr(self._manager, "runtime_status", "unavailable"))

    @property
    def runtime_error(self) -> str:
        return str(getattr(self._manager, "runtime_error", ""))

    def start_background_bootstrap(self) -> None:
        self._manager.start_background_bootstrap()

    def bootstrap_runtime(self) -> Any:
        return self._manager.bootstrap_runtime()

    def registry_entries(self) -> list[dict[str, Any]]:
        return self._manager.registry_entries()

    def registry_diagnostics(self) -> dict[str, Any]:
        return self._manager.registry_diagnostics()

    def extension_details(self, extension_id: str, *, ref: str | None = None) -> dict[str, Any]:
        ext_id = _require_extension_id(extension_id)
        safe_ref = str(ref or "").strip() or None
        return self._manager.extension_details(ext_id, ref=safe_ref)

    def installed_extensions(self) -> list[dict[str, Any]]:
        return self._manager.installed_extensions()

    def provider_rows(self, runtime: Any | None = None) -> list[dict[str, Any]]:
        return self._manager.provider_rows(runtime)

    def provider_catalog(self, *, runtime: Any | None = None, capability: str | None = None) -> dict[str, Any]:
        return self._manager.provider_catalog(runtime=runtime, capability=capability)

    def extension_tabs(self, *, runtime: Any | None = None) -> list[dict[str, Any]]:
        return self._manager.extension_tabs(runtime=runtime)

    def extension_tab_payload(self, extension_id: str, *, runtime: Any | None = None) -> dict[str, Any]:
        ext_id = _require_extension_id(extension_id)
        return self._manager.extension_tab_payload(ext_id, runtime=runtime)

    def ui_payload(self) -> dict[str, Any]:
        return self._manager.ui_payload()

    def run_extension_action(
        self,
        extension_id: str,
        action_id: str,
        *,
        payload: dict[str, Any] | None = None,
        runtime: Any | None = None,
    ) -> dict[str, Any]:
        ext_id = _require_extension_id(extension_id)
        act_id = _require_action_id(action_id)
        return self._manager.run_extension_action(ext_id, act_id, payload=payload, runtime=runtime)

    def restart_extension_sandbox(self, extension_id: str) -> dict[str, Any]:
        return self._manager.restart_extension_sandbox(_require_extension_id(extension_id))

    def kill_extension_sandbox(self, extension_id: str) -> dict[str, Any]:
        return self._manager.kill_extension_sandbox(_require_extension_id(extension_id))

    def resolve_asset_path(self, extension_id: str, asset_path: str) -> Path:
        return self._manager.resolve_asset_path(_require_extension_id(extension_id), asset_path)

    def install(
        self,
        extension_id: str,
        *,
        version: str | None = None,
        target: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ext_id = _require_extension_id(extension_id)
        safe_version = str(version or "").strip() or None
        safe_target = _sanitize_install_target(target)
        return self._manager.install(ext_id, version=safe_version, target=safe_target)

    def remove(self, extension_id: str) -> dict[str, Any]:
        return self._manager.remove(_require_extension_id(extension_id))

    def enable(self, extension_id: str) -> dict[str, Any]:
        return self._manager.enable(_require_extension_id(extension_id))

    def disable(self, extension_id: str) -> dict[str, Any]:
        return self._manager.disable(_require_extension_id(extension_id))
