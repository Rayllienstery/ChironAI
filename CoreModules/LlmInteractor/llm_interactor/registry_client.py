"""Registry discovery for extension catalogs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from llm_interactor.manifest import EXTENSION_API_VERSION


DEFAULT_REGISTRY_PATH = "extensions/registry/extensions.json"
SUPPORTED_REGISTRY_APPS = {"", "chironai", "chiron ai"}


@dataclass(frozen=True)
class ExtensionRegistryDiagnostic:
    severity: str
    code: str
    message: str
    index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.index is not None:
            payload["index"] = self.index
        return payload


@dataclass(frozen=True)
class ExtensionRegistryLoadResult:
    registry_url: str
    entries: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[ExtensionRegistryDiagnostic] = field(default_factory=list)


class ExtensionRegistryClient:
    """Loads an extension registry from file or URL."""

    def __init__(
        self,
        registry_url: str | None = None,
        *,
        project_root: Path | None = None,
        fallback_url: str | None = None,
    ) -> None:
        self._project_root = project_root or Path.cwd()
        self._registry_url = registry_url or self._default_registry_url()
        self._fallback_url = fallback_url or ""

    def _default_registry_url(self) -> str:
        return str((self._project_root / DEFAULT_REGISTRY_PATH).resolve())

    @property
    def registry_url(self) -> str:
        return self._registry_url

    @property
    def fallback_url(self) -> str:
        return self._fallback_url

    def load(self) -> list[dict[str, Any]]:
        return self.load_with_diagnostics().entries

    def load_with_diagnostics(self) -> ExtensionRegistryLoadResult:
        diagnostics: list[ExtensionRegistryDiagnostic] = []
        raw: Any
        active_url = self._registry_url
        try:
            raw = self._load_json_obj(active_url)
        except Exception as e:
            if self._fallback_url and self._fallback_url != active_url:
                diagnostics.append(
                    ExtensionRegistryDiagnostic(
                        severity="warning",
                        code="registry_load_failed_using_fallback",
                        message=f"{type(e).__name__}: {e}",
                    )
                )
                active_url = self._fallback_url
                try:
                    raw = self._load_json_obj(active_url)
                except Exception as fallback_error:
                    diagnostics.append(
                        ExtensionRegistryDiagnostic(
                            severity="error",
                            code="registry_fallback_load_failed",
                            message=f"{type(fallback_error).__name__}: {fallback_error}",
                        )
                    )
                    return ExtensionRegistryLoadResult(registry_url=active_url, diagnostics=diagnostics)
            else:
                return ExtensionRegistryLoadResult(
                    registry_url=active_url,
                    diagnostics=[
                        ExtensionRegistryDiagnostic(
                            severity="error",
                            code="registry_load_failed",
                            message=f"{type(e).__name__}: {e}",
                        )
                    ],
                )
        if isinstance(raw, dict) and isinstance(raw.get("extensions"), list):
            raw = raw["extensions"]
        if not isinstance(raw, list):
            return ExtensionRegistryLoadResult(
                registry_url=active_url,
                diagnostics=diagnostics + [
                    ExtensionRegistryDiagnostic(
                        severity="error",
                        code="registry_shape_invalid",
                        message="registry root must be a list or an object with an extensions list",
                    )
                ],
            )
        out: list[dict[str, Any]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                diagnostics.append(
                    ExtensionRegistryDiagnostic(
                        severity="error",
                        code="registry_entry_invalid",
                        message="registry entry must be an object",
                        index=index,
                    )
                )
                continue
            candidate = dict(item)
            entry_errors = self._validate_entry(candidate)
            if entry_errors:
                diagnostics.extend(
                    ExtensionRegistryDiagnostic(
                        severity="error",
                        code=code,
                        message=message,
                        index=index,
                    )
                    for code, message in entry_errors
                )
                continue
            out.append(candidate)
        return ExtensionRegistryLoadResult(registry_url=active_url, entries=out, diagnostics=diagnostics)

    def _validate_entry(self, entry: dict[str, Any]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        ext_id = str(entry.get("id") or "").strip()
        title = str(entry.get("title") or "").strip()
        repository = str(entry.get("repository") or entry.get("repo_url") or "").strip()
        source_path = str(entry.get("source_path") or "").strip()
        archive_url = str(entry.get("archive_url") or "").strip()
        if not ext_id:
            errors.append(("registry_entry_missing_id", "registry entry id is required"))
        if not title:
            errors.append(("registry_entry_missing_title", f"registry entry '{ext_id or '<unknown>'}' title is required"))
        if not (repository or source_path or archive_url):
            errors.append(
                (
                    "registry_entry_missing_source",
                    f"registry entry '{ext_id or '<unknown>'}' must define repository, source_path, or archive_url",
                )
            )
        compatibility = entry.get("compatibility")
        if compatibility is not None:
            if not isinstance(compatibility, dict):
                errors.append(("registry_entry_bad_compatibility", "registry compatibility must be an object"))
            else:
                api_version = str(compatibility.get("extension_api_version") or "").strip()
                app = str(compatibility.get("app") or "").strip().lower()
                if api_version and api_version != EXTENSION_API_VERSION:
                    errors.append(
                        (
                            "registry_entry_unsupported_api",
                            f"registry entry '{ext_id or '<unknown>'}' requires extension_api_version {api_version}",
                        )
                    )
                if app not in SUPPORTED_REGISTRY_APPS:
                    errors.append(
                        (
                            "registry_entry_unsupported_app",
                            f"registry entry '{ext_id or '<unknown>'}' targets unsupported app '{app}'",
                        )
                    )
        return errors

    def _load_json_obj(self, location: str) -> Any:
        parsed = urlparse(location)
        if parsed.scheme in ("http", "https"):
            resp = requests.get(location, timeout=30)
            resp.raise_for_status()
            return resp.json()
        if parsed.scheme == "file":
            path = Path(parsed.path)
        else:
            path = Path(location)
            if not path.is_absolute():
                path = (self._project_root / path).resolve()
        return json.loads(path.read_text(encoding="utf-8"))
