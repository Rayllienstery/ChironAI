"""High-level extension management for installation, loading, and diagnostics."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from llm_interactor.contracts import ProviderHostContext
from llm_interactor.discovery import FailedExtension, LoadedExtension, MANIFEST_FILENAME, discover_extensions
from llm_interactor.install_state import ExtensionsRepository, InstalledExtensionRecord
from llm_interactor.manifest import EXTENSION_TYPE_LLM_PROVIDER
from llm_interactor.registry_client import ExtensionRegistryClient
from llm_interactor.runtime import LLMRuntime, ProviderRegistry


DEFAULT_BUNDLED_DIR = "extensions/bundled"
DEFAULT_INSTALLED_DIR = "logs/extensions/installed"


@dataclass(frozen=True)
class RuntimeBootstrap:
    runtime: LLMRuntime
    registry: ProviderRegistry
    loaded: list[LoadedExtension]
    failed: list[FailedExtension]


class ExtensionManager:
    """Owns install state, discovery, and runtime bootstrap."""

    def __init__(
        self,
        *,
        project_root: Path,
        host_context: ProviderHostContext,
        settings_repo: Any,
        registry_client: ExtensionRegistryClient | None = None,
        bundled_dir: Path | None = None,
        installed_dir: Path | None = None,
        default_provider_id: str | None = None,
    ) -> None:
        self._project_root = project_root
        self._host_context = host_context
        self._settings_repo = settings_repo
        self._repo = ExtensionsRepository(settings_repo)
        self._registry_client = registry_client or ExtensionRegistryClient(project_root=project_root)
        self._bundled_dir = bundled_dir or (project_root / DEFAULT_BUNDLED_DIR)
        self._installed_dir = installed_dir or (project_root / DEFAULT_INSTALLED_DIR)
        self._installed_dir.mkdir(parents=True, exist_ok=True)
        self._default_provider_id = default_provider_id
        self._loaded: list[LoadedExtension] = []
        self._failed: list[FailedExtension] = []

    def ensure_builtin_installed(self, extension_id: str) -> None:
        bundled = self._bundled_dir / extension_id
        manifest_path = bundled / MANIFEST_FILENAME
        if not manifest_path.is_file():
            return
        try:
            from llm_interactor.discovery import load_manifest_from_dir

            manifest = load_manifest_from_dir(bundled)
        except Exception:
            return
        records = self._repo.list_records()
        existing = next((r for r in records if r.id == manifest.id), None)
        if existing is not None and not existing.installed:
            return
        if existing is not None and existing.version == manifest.version:
            target = self._installed_dir / manifest.id / manifest.version
            if target.is_dir():
                return
        target = self._installed_dir / manifest.id / manifest.version
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled, target, dirs_exist_ok=True)
        next_records = [r for r in records if r.id != manifest.id]
        next_records.append(
            InstalledExtensionRecord(
                id=manifest.id,
                version=manifest.version,
                enabled=True,
                installed=True,
                source={"type": "bundled", "path": str(bundled)},
                title=manifest.title,
                description=manifest.description,
                icon=manifest.icon,
                restart_required=False,
            )
        )
        self._repo.save_records(next_records)

    def ensure_bundled_installed(self) -> None:
        if not self._bundled_dir.is_dir():
            return
        for child in sorted(self._bundled_dir.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                self.ensure_builtin_installed(child.name)

    def bootstrap_runtime(self) -> RuntimeBootstrap:
        self.ensure_bundled_installed()
        records = [r for r in self._repo.list_records() if r.installed and r.enabled]
        source_dirs = [
            self._installed_dir / record.id / record.version
            for record in records
            if (self._installed_dir / record.id / record.version).is_dir()
        ]
        report = discover_extensions(
            source_dirs,
            host_context=self._host_context,
            enabled_extension_ids={r.id for r in records},
        )
        registry = ProviderRegistry()
        failed = list(report.failed)
        for loaded in report.loaded:
            if loaded.manifest.type != EXTENSION_TYPE_LLM_PROVIDER:
                continue
            try:
                registry.register(loaded.provider)
            except Exception as e:
                failed.append(
                    FailedExtension(
                        extension_id=loaded.manifest.id,
                        source_dir=loaded.source_dir,
                        error=f"{type(e).__name__}: {e}",
                        manifest=loaded.manifest,
                    )
                )
        self._loaded = list(report.loaded)
        self._failed = failed
        return RuntimeBootstrap(
            runtime=LLMRuntime(registry, default_provider_id=self._default_provider_id),
            registry=registry,
            loaded=self._loaded,
            failed=self._failed,
        )

    def registry_entries(self) -> list[dict[str, Any]]:
        return self._registry_client.load()

    def installed_extensions(self) -> list[dict[str, Any]]:
        loaded_by_id = {item.manifest.id: item for item in self._loaded}
        failed_by_id = {item.extension_id: item for item in self._failed}
        out: list[dict[str, Any]] = []
        for record in self._repo.list_records():
            if not record.installed:
                continue
            loaded = loaded_by_id.get(record.id)
            failed = failed_by_id.get(record.id)
            out.append(
                {
                    "id": record.id,
                    "version": record.version,
                    "enabled": bool(record.enabled),
                    "installed": bool(record.installed),
                    "restart_required": bool(record.restart_required),
                    "title": record.title or (loaded.manifest.title if loaded else record.id),
                    "description": record.description or (loaded.manifest.description if loaded else ""),
                    "icon": record.icon or (loaded.manifest.icon if loaded else ""),
                    "status": (
                        "loaded"
                        if loaded is not None
                        else "failed"
                        if failed is not None
                        else "installed"
                    ),
                    "error": failed.error if failed is not None else "",
                    "source": dict(record.source or {}),
                }
            )
        return out

    def provider_rows(self, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        rt = runtime
        rows: list[dict[str, Any]] = []
        if rt is not None:
            healths = {item.provider_id: item for item in rt.registry.healths()}
            models_by_provider: dict[str, list[dict[str, Any]]] = {}
            for model in rt.registry.list_models():
                models_by_provider.setdefault(model.provider_id, []).append(
                    {
                        "id": model.id,
                        "label": model.label,
                        "description": model.description,
                        "metadata": dict(model.metadata or {}),
                    }
                )
            for desc in rt.registry.descriptors():
                health = healths.get(desc.id)
                rows.append(
                    {
                        "provider_id": desc.id,
                        "extension_id": desc.extension_id,
                        "title": desc.title,
                        "description": desc.description,
                        "icon": desc.icon,
                        "capabilities": desc.capabilities.__dict__,
                        "health": {
                            "ok": bool(health.ok) if health else False,
                            "status": health.status if health else "unknown",
                            "message": health.message if health else "",
                            "details": dict(health.details or {}) if health else {},
                        },
                        "models": models_by_provider.get(desc.id, []),
                    }
                )
        return rows

    def provider_catalog(self, *, runtime: LLMRuntime | None = None, capability: str | None = None) -> dict[str, Any]:
        rows = self.provider_rows(runtime)
        cap = str(capability or "").strip().lower()
        if cap:
            rows = [
                row
                for row in rows
                if bool((row.get("capabilities") or {}).get(cap))
            ]
        flat_models: list[dict[str, Any]] = []
        for row in rows:
            for model in row.get("models") or []:
                flat_models.append(
                    {
                        "provider_id": row.get("provider_id"),
                        "provider_title": row.get("title"),
                        "extension_id": row.get("extension_id"),
                        "id": model.get("id"),
                        "name": model.get("label") or model.get("id"),
                        "label": model.get("label") or model.get("id"),
                        "description": model.get("description") or "",
                        "metadata": dict(model.get("metadata") or {}),
                    }
                )
        return {"providers": rows, "models": flat_models}

    def _find_loaded_extension(self, extension_id: str) -> LoadedExtension | None:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            return None
        for item in self._loaded:
            if item.manifest.id == ext_id:
                return item
        return None

    def extension_tabs(self, *, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in self._loaded:
            fn = getattr(item.provider, "get_tab_descriptor", None)
            if not callable(fn):
                continue
            try:
                raw = fn(runtime=runtime)
            except TypeError:
                raw = fn()
            if not isinstance(raw, dict):
                continue
            tab_id = str(raw.get("id") or "").strip() or item.manifest.id
            title = str(raw.get("title") or item.manifest.title).strip() or item.manifest.title
            out.append(
                {
                    "id": tab_id,
                    "extension_id": item.manifest.id,
                    "title": title,
                    "icon": str(raw.get("icon") or item.manifest.icon or ""),
                    "icon_url": str(raw.get("icon_url") or ""),
                    "description": str(raw.get("description") or item.manifest.description or ""),
                    "order": int(raw.get("order") or 0),
                    "status": dict(raw.get("status") or {}) if isinstance(raw.get("status"), dict) else None,
                }
            )
        out.sort(key=lambda row: (int(row.get("order") or 0), str(row.get("title") or "").lower()))
        return out

    def extension_tab_payload(self, extension_id: str, *, runtime: LLMRuntime | None = None) -> dict[str, Any]:
        item = self._find_loaded_extension(extension_id)
        if item is None:
            raise ValueError(f"Extension '{extension_id}' is not loaded")
        fn = getattr(item.provider, "get_tab_payload", None)
        if not callable(fn):
            return {
                "extension_id": item.manifest.id,
                "title": item.manifest.title,
                "icon": item.manifest.icon,
                "schema": dict(item.manifest.ui_schema or {}),
            }
        try:
            payload = fn(runtime=runtime)
        except TypeError:
            payload = fn()
        if not isinstance(payload, dict):
            raise ValueError(f"Extension '{extension_id}' returned invalid tab payload")
        return {
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            **payload,
        }

    def run_extension_action(
        self,
        extension_id: str,
        action_id: str,
        *,
        payload: dict[str, Any] | None = None,
        runtime: LLMRuntime | None = None,
    ) -> dict[str, Any]:
        item = self._find_loaded_extension(extension_id)
        if item is None:
            raise ValueError(f"Extension '{extension_id}' is not loaded")
        fn = getattr(item.provider, "run_action", None)
        if not callable(fn):
            raise ValueError(f"Extension '{extension_id}' does not expose actions")
        try:
            result = fn(str(action_id or "").strip(), dict(payload or {}), runtime=runtime)
        except TypeError:
            result = fn(str(action_id or "").strip(), dict(payload or {}))
        if isinstance(result, dict):
            return result
        return {"ok": True, "result": result}

    def ui_payload(self) -> dict[str, Any]:
        return {
            "extensions": [
                {
                    "id": item.manifest.id,
                    "title": item.manifest.title,
                    "description": item.manifest.description,
                    "icon": item.manifest.icon,
                    "settings_schema": item.manifest.settings_schema,
                    "ui_schema": item.manifest.ui_schema,
                }
                for item in self._loaded
            ],
            "failed": [
                {
                    "id": item.extension_id,
                    "error": item.error,
                }
                for item in self._failed
            ],
        }

    def install(self, extension_id: str, *, version: str | None = None) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        entry = next((item for item in self.registry_entries() if str(item.get("id") or "").strip() == ext_id), None)
        if entry is None:
            raise ValueError(f"Extension '{ext_id}' not found in registry")
        target_version = str(version or entry.get("latest_version") or entry.get("default_ref") or "").strip()
        if not target_version:
            raise ValueError("registry entry has no latest_version/default_ref")
        target_dir = self._installed_dir / ext_id / target_version
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        self._install_entry_payload(entry, target_dir)
        records = [r for r in self._repo.list_records() if r.id != ext_id]
        records.append(
            InstalledExtensionRecord(
                id=ext_id,
                version=target_version,
                enabled=True,
                installed=True,
                source={k: v for k, v in entry.items() if k in {"repo_url", "source_path", "archive_url", "default_ref"}},
                title=str(entry.get("title") or ext_id),
                description=str(entry.get("description") or ""),
                icon=str(entry.get("icon") or ""),
                restart_required=True,
            )
        )
        self._repo.save_records(records)
        return {"id": ext_id, "version": target_version, "restart_required": True, "status": "installed"}

    def _install_entry_payload(self, entry: dict[str, Any], target_dir: Path) -> None:
        source_path = str(entry.get("source_path") or "").strip()
        archive_url = str(entry.get("archive_url") or "").strip()
        repo_url = str(entry.get("repo_url") or "").strip()
        if source_path:
            src = Path(source_path)
            if not src.is_absolute():
                src = (self._project_root / src).resolve()
            if not src.is_dir():
                raise FileNotFoundError(f"extension source_path not found: {src}")
            shutil.copytree(src, target_dir, dirs_exist_ok=True)
            return
        if archive_url:
            self._download_zip_to_dir(archive_url, target_dir)
            return
        if repo_url and repo_url.endswith(".zip"):
            self._download_zip_to_dir(repo_url, target_dir)
            return
        raise ValueError("registry entry must define source_path or archive_url/repo_url zip")

    def _download_zip_to_dir(self, url: str, target_dir: Path) -> None:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(resp.content)
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path) as zf:
                members = zf.namelist()
                root_prefix = ""
                if members:
                    first = members[0].split("/")[0]
                    if first:
                        root_prefix = first + "/"
                zf.extractall(target_dir.parent)
                extracted_root = target_dir.parent / root_prefix.rstrip("/")
                if extracted_root.is_dir() and extracted_root != target_dir:
                    if target_dir.exists():
                        shutil.rmtree(target_dir)
                    shutil.move(str(extracted_root), str(target_dir))
        finally:
            tmp_path.unlink(missing_ok=True)

    def _rewrite_record(self, extension_id: str, fn) -> dict[str, Any]:
        records = self._repo.list_records()
        out: list[InstalledExtensionRecord] = []
        result: InstalledExtensionRecord | None = None
        for record in records:
            if record.id == extension_id:
                record = fn(record)
                result = record
            out.append(record)
        if result is None:
            raise ValueError(f"Extension '{extension_id}' is not installed")
        self._repo.save_records(out)
        return {
            "id": result.id,
            "version": result.version,
            "enabled": result.enabled,
            "restart_required": result.restart_required,
        }

    def enable(self, extension_id: str) -> dict[str, Any]:
        return self._rewrite_record(
            extension_id,
            lambda r: InstalledExtensionRecord(**{**r.__dict__, "enabled": True, "restart_required": True}),
        )

    def disable(self, extension_id: str) -> dict[str, Any]:
        return self._rewrite_record(
            extension_id,
            lambda r: InstalledExtensionRecord(**{**r.__dict__, "enabled": False, "restart_required": True}),
        )

    def remove(self, extension_id: str) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        records = self._repo.list_records()
        target = next((r for r in records if r.id == ext_id), None)
        if target is None:
            raise ValueError(f"Extension '{ext_id}' is not installed")
        install_dir = self._installed_dir / target.id / target.version
        if install_dir.exists():
            shutil.rmtree(install_dir, ignore_errors=True)
        tombstone = InstalledExtensionRecord(
            id=target.id,
            version=target.version,
            enabled=False,
            installed=False,
            source=dict(target.source or {}),
            title=target.title,
            description=target.description,
            icon=target.icon,
            restart_required=True,
        )
        self._repo.save_records([r for r in records if r.id != ext_id] + [tombstone])
        return {"id": ext_id, "removed": True, "restart_required": True}
