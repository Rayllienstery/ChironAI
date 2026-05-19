"""High-level extension management for installation, loading, and diagnostics."""

from __future__ import annotations

import shutil
import threading
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from chironai_security import audit_extension_or_raise
from llm_interactor.contracts import ProviderHostContext
from llm_interactor.discovery import FailedExtension, LoadedExtension, MANIFEST_FILENAME, discover_extensions, load_manifest_from_dir
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
        self._runtime: LLMRuntime | None = None
        self._registry: ProviderRegistry | None = None
        self._runtime_status = "not_started"
        self._runtime_error = ""
        self._bootstrap_thread: threading.Thread | None = None
        self._provider_rows_cache: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def runtime_status(self) -> str:
        with self._lock:
            return self._runtime_status

    @property
    def runtime_error(self) -> str:
        with self._lock:
            return self._runtime_error

    @property
    def runtime(self) -> LLMRuntime | None:
        with self._lock:
            return self._runtime

    @property
    def registry(self) -> ProviderRegistry | None:
        with self._lock:
            return self._registry

    def start_background_bootstrap(self) -> None:
        """Start provider loading without blocking callers that only need manifests."""
        with self._lock:
            if self._runtime_status in {"loading", "ready"}:
                return
            self._runtime_status = "loading"
            self._runtime_error = ""
            self.ensure_bundled_installed()
            thread = threading.Thread(
                target=self._bootstrap_runtime_worker,
                name="chironai-extension-bootstrap",
                daemon=True,
            )
            self._bootstrap_thread = thread
            thread.start()

    def _bootstrap_runtime_worker(self) -> None:
        try:
            self.bootstrap_runtime()
        except Exception as e:  # pragma: no cover - defensive process resilience
            with self._lock:
                self._runtime_status = "failed"
                self._runtime_error = f"{type(e).__name__}: {e}"

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
        target = self._installed_dir / manifest.id / manifest.version
        if existing is not None and existing.version == manifest.version and target.is_dir():
            source_type = str((existing.source or {}).get("type") or "").strip().lower()
            if source_type and source_type != "bundled":
                return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.copytree(bundled, target)
        next_records = [r for r in records if r.id != manifest.id]
        next_records.append(
            InstalledExtensionRecord(
                id=manifest.id,
                version=manifest.version,
                enabled=existing.enabled if existing is not None else True,
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
        with self._lock:
            self._runtime_status = "loading"
            self._runtime_error = ""
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
        runtime = LLMRuntime(registry, default_provider_id=self._default_provider_id)
        provider_rows_cache = self._provider_rows_from_runtime(runtime)
        bootstrap = RuntimeBootstrap(
            runtime=runtime,
            registry=registry,
            loaded=self._loaded,
            failed=self._failed,
        )
        with self._lock:
            self._runtime = bootstrap.runtime
            self._registry = bootstrap.registry
            self._provider_rows_cache = provider_rows_cache
            self._runtime_status = "ready"
            self._runtime_error = ""
        return bootstrap

    def _asset_url(self, extension_id: str, icon: str) -> str:
        rel = str(icon or "").strip().replace("\\", "/")
        if not rel or rel.startswith(("http://", "https://", "data:")):
            return rel
        if rel.startswith("/") or ".." in rel.split("/"):
            return ""
        return f"/api/webui/extensions/{quote(str(extension_id), safe='')}/assets/{quote(rel, safe='/')}"

    def resolve_asset_path(self, extension_id: str, asset_path: str) -> Path:
        ext_id = str(extension_id or "").strip()
        rel = str(asset_path or "").strip().replace("\\", "/")
        if not ext_id or not rel or rel.startswith("/") or ".." in rel.split("/"):
            raise FileNotFoundError("extension asset not found")
        records = [
            record
            for record in self._repo.list_records()
            if record.installed and record.id == ext_id
        ]
        for record in records:
            root = (self._installed_dir / record.id / record.version).resolve()
            candidate = (root / rel).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("extension asset not found")

    def _installed_manifest_rows(self, *, enabled_only: bool = False) -> list[tuple[InstalledExtensionRecord, Path, Any]]:
        from llm_interactor.discovery import load_manifest_from_dir

        rows: list[tuple[InstalledExtensionRecord, Path, Any]] = []
        for record in self._repo.list_records():
            if not record.installed:
                continue
            if enabled_only and not record.enabled:
                continue
            source_dir = self._installed_dir / record.id / record.version
            if not source_dir.is_dir():
                continue
            try:
                rows.append((record, source_dir, load_manifest_from_dir(source_dir)))
            except Exception:
                continue
        return rows

    def _manifest_tab_ui(self, manifest: Any) -> dict[str, Any]:
        metadata = getattr(manifest, "metadata", {})
        if isinstance(metadata, dict) and isinstance(metadata.get("tab_ui"), dict):
            return dict(metadata["tab_ui"])
        raw = getattr(manifest, "tab_ui", None)
        return dict(raw) if isinstance(raw, dict) else {}

    def _manifest_tabs(self) -> list[dict[str, Any]]:
        failed_by_id = {item.extension_id: item for item in self._failed}
        out: list[dict[str, Any]] = []
        for record, _source_dir, manifest in self._installed_manifest_rows(enabled_only=True):
            tab_ui = self._manifest_tab_ui(manifest)
            capabilities = getattr(manifest, "capabilities", {}) or {}
            if not tab_ui and not bool(capabilities.get("tab_ui")):
                continue
            icon = str(tab_ui.get("icon") or getattr(manifest, "icon", "") or "")
            failed = failed_by_id.get(record.id)
            status = {
                "runtime": "failed" if failed else self.runtime_status,
                "tone": "error" if failed else "loading",
                "message": failed.error if failed else "Extension runtime is loading",
                "running": False,
            }
            out.append(
                {
                    "id": str(tab_ui.get("id") or getattr(manifest, "id", record.id)).strip() or record.id,
                    "extension_id": getattr(manifest, "id", record.id),
                    "title": str(tab_ui.get("title") or getattr(manifest, "title", record.title or record.id)).strip()
                    or record.id,
                    "icon": icon,
                    "icon_url": self._asset_url(getattr(manifest, "id", record.id), icon),
                    "description": str(getattr(manifest, "description", "") or ""),
                    "frame": dict(tab_ui.get("frame") or {}) if isinstance(tab_ui.get("frame"), dict) else {},
                    "order": int(tab_ui.get("order") or 0),
                    "status": status,
                }
            )
        out.sort(key=lambda row: (int(row.get("order") or 0), str(row.get("title") or "").lower()))
        return out

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
                    "icon_url": self._asset_url(record.id, record.icon or (loaded.manifest.icon if loaded else "")),
                    "status": (
                        "loaded"
                        if loaded is not None
                        else "failed"
                        if failed is not None
                        else "installed"
                    ),
                    "error": failed.error if failed is not None else "",
                    "security_blocked": bool(failed.security_findings) if failed is not None else False,
                    "security_findings": list(failed.security_findings) if failed is not None else [],
                    "source": dict(record.source or {}),
                }
            )
        return out

    def _provider_rows_from_runtime(self, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
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
                        "icon_url": self._asset_url(desc.extension_id, desc.icon),
                        "capabilities": desc.capabilities.__dict__,
                        "metadata": dict(desc.metadata or {}),
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

    def provider_rows(self, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if self._provider_rows_cache:
                return [dict(row) for row in self._provider_rows_cache]
        rt = runtime
        if rt is None:
            rt = self.runtime
        if rt is None:
            return []
        return self._provider_rows_from_runtime(rt)

    def provider_catalog(self, *, runtime: LLMRuntime | None = None, capability: str | None = None) -> dict[str, Any]:
        if runtime is None:
            runtime = self.runtime
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
                        "provider_icon_url": row.get("icon_url"),
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
        if runtime is None:
            runtime = self.runtime
        if runtime is None:
            return self._manifest_tabs()
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
                    "icon_url": str(raw.get("icon_url") or "")
                    or self._asset_url(item.manifest.id, str(raw.get("icon") or item.manifest.icon or "")),
                    "description": str(raw.get("description") or item.manifest.description or ""),
                    "frame": dict(raw.get("frame") or {}) if isinstance(raw.get("frame"), dict) else {},
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
            "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
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
                    "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
                    "settings_schema": item.manifest.settings_schema,
                    "ui_schema": item.manifest.ui_schema,
                }
                for item in self._loaded
            ],
            "failed": [
                {
                    "id": item.extension_id,
                    "error": item.error,
                    "security_findings": list(item.security_findings),
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
        try:
            self._install_entry_payload(entry, target_dir)
            manifest = load_manifest_from_dir(target_dir)
            if manifest.backend is None:
                raise ValueError("manifest backend is required")
            audit_extension_or_raise(target_dir, manifest=manifest, entrypoint=manifest.backend.entrypoint)
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise
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
                infos = [info for info in zf.infolist() if info.filename and not info.filename.endswith("/")]
                names = [info.filename.replace("\\", "/") for info in infos]
                for name in names:
                    parts = [part for part in name.split("/") if part]
                    if (
                        not parts
                        or name.startswith("/")
                        or ":" in parts[0]
                        or any(part == ".." for part in parts)
                    ):
                        raise ValueError(f"unsafe zip member path: {name}")
                root_prefix = ""
                if names:
                    first = names[0].split("/")[0]
                    if first and all(name == first or name.startswith(first + "/") for name in names):
                        root_prefix = first + "/"
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                for info in infos:
                    name = info.filename.replace("\\", "/")
                    rel = name[len(root_prefix):] if root_prefix and name.startswith(root_prefix) else name
                    if not rel:
                        continue
                    dest = (target_dir / rel).resolve()
                    root = target_dir.resolve()
                    try:
                        dest.relative_to(root)
                    except ValueError as e:
                        raise ValueError(f"unsafe zip member path: {name}") from e
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, dest.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
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
