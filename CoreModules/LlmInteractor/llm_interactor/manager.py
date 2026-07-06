"""High-level extension management for installation, loading, and diagnostics."""

from __future__ import annotations

import contextlib
import logging
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from chironai_security import audit_extension_or_raise

from llm_interactor.contracts import ProviderHostContext
from llm_interactor.discovery import (
    MANIFEST_FILENAME,
    FailedExtension,
    LoadedExtension,
    load_manifest_from_dir,
)
from llm_interactor.install_state import ExtensionsRepository, InstalledExtensionRecord
from llm_interactor.manager_archive import (
    download_extension_zip_to_dir,
    github_archive_url,
    github_raw_asset_url,
    install_storage_segment,
    path_contains_symlink,
    validate_archive_url,
)
from llm_interactor.manager_blocklist import (
    RESTART_SCOPE_PROVIDER_REGISTRY,
    blocklist_match_for_entry,
    blocklist_match_for_record,
    blocklist_match_for_values,
    disable_blocklisted_records,
    disable_security_blocked_extensions,
)
from llm_interactor.manager_bootstrap import (
    RuntimeBootstrap,
    discover_runtime_extensions,
    ensure_required_bundled_enabled,
    prewarm_provider_rows_async,
    record_bootstrap_timing,
    source_dirs_for_records,
)
from llm_interactor.manager_extension_tabs import (
    ExtensionTabCacheEntry,
    ExtensionTabMixin,
)
from llm_interactor.manager_install_helpers import (
    capability_expansion,
    install_provenance,
    resolve_install_target,
    utc_now_iso,
    validate_install_manifest,
)
from llm_interactor.manager_provider_catalog import (
    build_provider_catalog,
    provider_rows_from_runtime,
    sandbox_diagnostics,
)
from llm_interactor.manager_registry import (
    fetch_extension_details,
    load_registry_entries,
    registry_diagnostics_payload,
)
from llm_interactor.manifest import EXTENSION_TYPE_LLM_PROVIDER
from llm_interactor.runtime import LLMRuntime, ProviderRegistry

_log = logging.getLogger(__name__)

DEFAULT_BUNDLED_DIR = "extensions/bundled"
DEFAULT_INSTALLED_DIR = "logs/extensions/installed"


def _utc_now() -> str:
    return utc_now_iso()


class ExtensionManager(ExtensionTabMixin):
    """Owns install state, discovery, and runtime bootstrap."""

    def __init__(
        self,
        *,
        project_root: Path,
        host_context: ProviderHostContext,
        settings_repo: Any,
        registry_client: Any,
        bundled_dir: Path | None = None,
        installed_dir: Path | None = None,
        default_provider_id: str | None = None,
        use_sandbox: bool = True,
        repository_client: Any | None = None,
        blocklist_policy: Any | None = None,
    ) -> None:
        self._project_root = project_root
        self._host_context = host_context
        self._settings_repo = settings_repo
        self._repo = ExtensionsRepository(settings_repo)
        if registry_client is None:
            raise TypeError(
                "registry_client is required; construct the host stack via extensions_host "
                "or inject registry clients from the extension-management backend"
            )
        self._registry_client = registry_client
        if repository_client is not None:
            self._repository_client = repository_client
        else:
            self._repository_client = None
        self._blocklist_policy = blocklist_policy
        self._bundled_dir = bundled_dir or (project_root / DEFAULT_BUNDLED_DIR)
        self._installed_dir = installed_dir or (project_root / DEFAULT_INSTALLED_DIR)
        self._installed_dir.mkdir(parents=True, exist_ok=True)
        self._default_provider_id = default_provider_id
        self._use_sandbox = bool(use_sandbox)
        self._loaded: list[LoadedExtension] = []
        self._failed: list[FailedExtension] = []
        self._runtime: LLMRuntime | None = None
        self._registry: ProviderRegistry | None = None
        self._runtime_status = "not_started"
        self._runtime_error = ""
        self._bootstrap_thread: threading.Thread | None = None
        self._provider_rows_cache: list[dict[str, Any]] = []
        self._tab_cache: dict[str, ExtensionTabCacheEntry] = {}
        self._tab_cache_generation = 0
        self._lock = threading.RLock()
        # Serializes concurrent bootstrap_runtime() calls (background + sync).
        # Prevents double-starting sandboxes and state corruption when install/
        # enable triggers a sync reload while the background worker is running.
        self._bootstrap_lock = threading.Lock()

    def _shutdown_loaded_extensions(self, loaded: list[LoadedExtension] | None = None) -> None:
        for item in list(loaded if loaded is not None else self._loaded):
            close = getattr(item.provider, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()

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
        """Start provider loading without blocking callers that only need manifests.

        Only the status flag is set under the lock; all I/O (bundled copy,
        blocklist fetch, sandbox startup) happens in the background thread via
        bootstrap_runtime() → _bootstrap_runtime_body().  This avoids blocking
        every reader of runtime_status/runtime/registry during startup.
        """
        with self._lock:
            if self._runtime_status in {"loading", "ready"}:
                return
            self._runtime_status = "loading"
            self._runtime_error = ""
            # Discard any stale in-process registry cache so the first UI
            # request always fetches a fresh copy from the remote source.
            self.invalidate_registry_cache()
            thread = threading.Thread(
                target=self._bootstrap_runtime_worker,
                name="chironai-extension-bootstrap",
                daemon=True,
            )
            self._bootstrap_thread = thread
            thread.start()
            # Pre-warm the registry cache in a separate thread so the first
            # tab open is instant.  Runs in parallel with the bootstrap worker
            # and does not block provider loading.
            threading.Thread(
                target=self._prewarm_registry,
                name="chironai-registry-prewarm",
                daemon=True,
            ).start()

    def _prewarm_registry(self) -> None:
        with contextlib.suppress(Exception):
            self._registry_client.load_with_diagnostics()

    def _bootstrap_runtime_worker(self) -> None:
        try:
            # bootstrap_runtime() acquires _bootstrap_lock, serializing against
            # any concurrent sync call from install/enable/disable/remove.
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
        match = self._blocklist_match_for_values(
            extension_id=manifest.id,
            version=manifest.version,
            ref=manifest.version,
            source_path=str(bundled),
        )
        if match.get("matched"):
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
                restart_scope="none",
                provenance={
                    "provenance_level": "local_source",
                    "selected_version": manifest.version,
                    "selected_ref": manifest.version,
                    "source_path": str(bundled),
                },
                security_scan={"status": "passed", "scanner": "chironai_static_audit"},
                capabilities=dict(getattr(manifest, "capabilities", {}) or {}),
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
        with self._bootstrap_lock:
            return self._bootstrap_runtime_body()

    def _bootstrap_runtime_body(self) -> RuntimeBootstrap:
        import time as _time

        _t_bootstrap_start = _time.perf_counter()

        with self._lock:
            self._runtime_status = "loading"
            self._runtime_error = ""

        _t_bundled = _time.perf_counter()
        self.ensure_bundled_installed()
        self._disable_blocklisted_records()
        ensure_required_bundled_enabled(
            repo=self._repo,
            blocklist_match_for_record=self._blocklist_match_for_record,
        )
        _bundled_ms = (_time.perf_counter() - _t_bundled) * 1000

        records = [r for r in self._repo.list_records() if r.installed and r.enabled]
        source_dirs = source_dirs_for_records(records, self._installed_dir)

        _t_discover = _time.perf_counter()
        bootstrap = discover_runtime_extensions(
            source_dirs=source_dirs,
            host_context=self._host_context,
            enabled_extension_ids={r.id for r in records},
            use_sandbox=self._use_sandbox,
            default_provider_id=self._default_provider_id,
            on_security_blocked=self._disable_security_blocked_extensions,
        )
        try:
            from application.host_provider_sync import sync_custom_openai_providers

            sync_custom_openai_providers(bootstrap.registry, self._settings_repo)
        except Exception as exc:
            _log.warning("custom OpenAI provider sync failed: %s", exc)
        _discover_ms = (_time.perf_counter() - _t_discover) * 1000
        previous_loaded = self._loaded
        runtime = bootstrap.runtime
        with self._lock:
            self._shutdown_loaded_extensions(previous_loaded)
            self._loaded = list(bootstrap.loaded)
            self._failed = list(bootstrap.failed)
            self._runtime = bootstrap.runtime
            self._registry = bootstrap.registry
            self._provider_rows_cache = []
            self._mark_tab_cache_stale()
            self._runtime_status = "ready"
            self._runtime_error = ""

        record_bootstrap_timing(
            bootstrap_start=_t_bootstrap_start,
            bundled_start=_t_bundled,
            discover_start=_t_discover,
            bootstrap=bootstrap,
            source_dir_count=len(source_dirs),
            bundled_ms=_bundled_ms,
            discover_ms=_discover_ms,
            bootstrap_total_ms=(_time.perf_counter() - _t_bootstrap_start) * 1000,
        )
        prewarm_provider_rows_async(
            runtime,
            provider_rows_fn=lambda rt: provider_rows_from_runtime(rt, asset_url=self._asset_url),
            cache_lock=self._lock,
            cache=self._provider_rows_cache,
        )
        for loaded in bootstrap.loaded:
            if loaded.manifest.type == EXTENSION_TYPE_LLM_PROVIDER:
                self.refresh_extension_tab(loaded.manifest.id, runtime=runtime)
        return bootstrap

    def _disable_security_blocked_extensions(self, failed: list[FailedExtension]) -> None:
        disable_security_blocked_extensions(failed, repo=self._repo, utc_now=_utc_now)

    def _disable_blocklisted_records(self) -> None:
        disable_blocklisted_records(
            repo=self._repo,
            blocklist_policy=self._blocklist_policy,
            utc_now=_utc_now,
        )

    def _blocklist_match_for_values(
        self,
        *,
        extension_id: str,
        version: str = "",
        ref: str = "",
        repository: str = "",
        repository_id: str = "",
        publisher: str = "",
        source_path: str = "",
    ) -> dict[str, Any]:
        return blocklist_match_for_values(
            self._blocklist_policy,
            extension_id=extension_id,
            version=version,
            ref=ref,
            repository=repository,
            repository_id=repository_id,
            publisher=publisher,
            source_path=source_path,
        )

    def _blocklist_match_for_entry(self, entry: dict[str, Any], *, version: str = "", ref: str = "") -> dict[str, Any]:
        return blocklist_match_for_entry(self._blocklist_policy, entry, version=version, ref=ref)

    def _blocklist_match_for_record(self, record: InstalledExtensionRecord) -> dict[str, Any]:
        return blocklist_match_for_record(self._blocklist_policy, record)

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
            lexical_candidate = root / rel
            candidate = lexical_candidate.resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if path_contains_symlink(root, lexical_candidate):
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
        with self._lock:
            failed_snapshot = list(self._failed)
        failed_by_id = {item.extension_id: item for item in failed_snapshot}
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

    def invalidate_registry_cache(self) -> None:
        """Discard the in-process registry cache so the next call re-fetches from the source."""
        invalidate = getattr(self._registry_client, "invalidate_cache", None)
        if callable(invalidate):
            invalidate()

    def registry_entries(self) -> list[dict[str, Any]]:
        return load_registry_entries(
            self._registry_client,
            blocklist_match_fn=self._blocklist_match_for_entry,
            github_raw_asset_url_fn=github_raw_asset_url,
        )

    def registry_diagnostics(self) -> dict[str, Any]:
        return registry_diagnostics_payload(
            self._registry_client,
            registry_entries_fn=self.registry_entries,
        )

    def extension_details(self, extension_id: str, *, ref: str | None = None) -> dict[str, Any]:
        return fetch_extension_details(
            extension_id,
            registry_entries_fn=self.registry_entries,
            repository_client=self._repository_client,
            ref=ref,
        )

    def installed_extensions(self) -> list[dict[str, Any]]:
        with self._lock:
            loaded_snapshot = list(self._loaded)
            failed_snapshot = list(self._failed)
        loaded_by_id = {item.manifest.id: item for item in loaded_snapshot}
        failed_by_id = {item.extension_id: item for item in failed_snapshot}
        out: list[dict[str, Any]] = []
        for record in self._repo.list_records():
            if not record.installed:
                continue
            loaded = loaded_by_id.get(record.id)
            failed = failed_by_id.get(record.id)
            sandbox = sandbox_diagnostics(loaded, failed)
            blocklist = self._blocklist_match_for_record(record)
            status = "loaded" if loaded is not None else "failed" if failed is not None else "installed"
            if blocklist.get("matched") or str((record.security_scan or {}).get("status") or "") == "blocked":
                status = "blocked"
            if loaded is not None and sandbox["sandbox_status"] in {
                "blocked",
                "crashed",
                "timeout",
                "protocol_error",
                "manual_stop",
            }:
                status = "failed"
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
                    "status": status,
                    "error": failed.error if failed is not None else "",
                    "security_blocked": bool(failed.security_findings)
                    if failed is not None
                    else bool(blocklist.get("matched"))
                    or str((record.security_scan or {}).get("status") or "") == "blocked",
                    "security_findings": list(failed.security_findings)
                    if failed is not None
                    else list((record.security_scan or {}).get("findings") or []),
                    **sandbox,
                    "source": dict(record.source or {}),
                    "provenance": dict(record.provenance or {}),
                    "security_scan": dict(record.security_scan or {}),
                    "blocklist": blocklist,
                    "capabilities": dict(record.capabilities or {}),
                    "blocked_reason": record.blocked_reason,
                    "restart_scope": str(record.restart_scope or "none"),
                }
            )
        return out

    def provider_rows(self, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if self._provider_rows_cache:
                return [dict(row) for row in self._provider_rows_cache]
        rt = runtime
        if rt is None:
            rt = self.runtime
        if rt is None:
            return []
        return provider_rows_from_runtime(rt, asset_url=self._asset_url)

    def provider_catalog(self, *, runtime: LLMRuntime | None = None, capability: str | None = None) -> dict[str, Any]:
        if runtime is None:
            runtime = self.runtime
        rows = self.provider_rows(runtime)
        return build_provider_catalog(rows, capability=capability)

    def invalidate_provider_rows_cache(self) -> None:
        with self._lock:
            self._provider_rows_cache = []

    def _find_loaded_extension(self, extension_id: str) -> LoadedExtension | None:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            return None
        with self._lock:
            snapshot = list(self._loaded)
        for item in snapshot:
            if item.manifest.id == ext_id:
                return item
        return None

    def _manifest_for_extension(self, extension_id: str) -> tuple[InstalledExtensionRecord, Any] | None:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            return None
        for record, _source_dir, manifest in self._installed_manifest_rows(enabled_only=True):
            if str(getattr(manifest, "id", record.id)) == ext_id or record.id == ext_id:
                return record, manifest
        return None

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
        self.invalidate_extension_tab_cache(extension_id)
        if isinstance(result, dict):
            return result
        return {"ok": True, "result": result}

    def restart_extension_sandbox(self, extension_id: str) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        # Phase 1: read current state and validate under lock (no I/O).
        with self._lock:
            item = self._find_loaded_extension(ext_id)
            if item is not None:
                restart_fn = getattr(item.provider, "restart_sandbox", None)
                if not callable(restart_fn):
                    raise ValueError(f"Extension '{ext_id}' is not sandboxed")
        if item is None:
            # Failed-extension restart also performs subprocess I/O outside the lock.
            return self._restart_failed_extension_sandbox(ext_id)
        # Phase 2: restart sandbox subprocess WITHOUT holding the lock.
        # ExtensionWorkerClient.restart() terminates the old process, spawns a new
        # one, and sends an initialize RPC (up to 8 s timeout).  Holding self._lock
        # throughout would freeze every reader of runtime/registry/status.
        restart_fn()
        # Phase 3: invalidate cache and snapshot diagnostics under lock.
        with self._lock:
            self._provider_rows_cache = []
            sandbox = sandbox_diagnostics(item)
        self.invalidate_extension_tab_cache(ext_id)
        return {"id": ext_id, "ok": True, "action": "restart", **sandbox}

    def kill_extension_sandbox(self, extension_id: str) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        with self._lock:
            item = self._find_loaded_extension(ext_id)
            if item is None:
                raise ValueError(f"Extension '{ext_id}' is not loaded")
            kill = getattr(item.provider, "kill_sandbox", None)
            if not callable(kill):
                raise ValueError(f"Extension '{ext_id}' is not sandboxed")
            kill()
            sandbox = sandbox_diagnostics(item)
        self.invalidate_extension_tab_cache(ext_id)
        return {"id": ext_id, "ok": True, "action": "kill", **sandbox}

    def _restart_failed_extension_sandbox(self, extension_id: str) -> dict[str, Any]:
        # Phase 1: read failed-extension state under lock.
        with self._lock:
            failed = next((item for item in self._failed if item.extension_id == extension_id), None)
        if failed is None:
            raise ValueError(f"Extension '{extension_id}' is not loaded")
        if failed.security_findings:
            raise ValueError(f"Extension '{extension_id}' is security blocked")
        manifest = failed.manifest or load_manifest_from_dir(failed.source_dir)
        if manifest.backend is None:
            raise ValueError("manifest backend is required")
        # Phase 2: re-run security audit before restart.  Extension files may have
        # been modified between the initial load failure and this restart attempt.
        audit_extension_or_raise(failed.source_dir, manifest=manifest, entrypoint=manifest.backend.entrypoint)
        # Phase 3: start sandboxed provider WITHOUT holding the lock.
        # Subprocess startup + initialize RPC can take several seconds.
        from extensions_sandbox import start_sandboxed_extension_provider

        provider = start_sandboxed_extension_provider(
            source_dir=failed.source_dir,
            entrypoint=manifest.backend.entrypoint,
            manifest=manifest,
            host_context=self._host_context,
        )
        loaded = LoadedExtension(
            manifest=manifest,
            source_dir=failed.source_dir,
            provider=provider,
            sandboxed=True,
            sandbox_status=str(getattr(provider, "sandbox_status", "ready") or "ready"),
        )
        # Phase 4: update runtime state under lock.
        with self._lock:
            if manifest.type == EXTENSION_TYPE_LLM_PROVIDER and self._registry is not None:
                self._registry.register(provider)
            self._loaded = [item for item in self._loaded if item.manifest.id != extension_id] + [loaded]
            self._failed = [item for item in self._failed if item.extension_id != extension_id]
            self._provider_rows_cache = []
            sandbox = sandbox_diagnostics(loaded)
        return {"id": extension_id, "ok": True, "action": "restart", **sandbox}

    def ui_payload(self) -> dict[str, Any]:
        with self._lock:
            loaded_snapshot = list(self._loaded)
            failed_snapshot = list(self._failed)
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
                for item in loaded_snapshot
            ],
            "failed": [
                {
                    "id": item.extension_id,
                    "error": item.error,
                    "security_findings": list(item.security_findings),
                    **sandbox_diagnostics(None, item),
                }
                for item in failed_snapshot
            ],
        }

    def install(
        self,
        extension_id: str,
        *,
        version: str | None = None,
        target: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        entry = next((item for item in self.registry_entries() if str(item.get("id") or "").strip() == ext_id), None)
        if entry is None:
            raise ValueError(f"Extension '{ext_id}' not found in registry")
        target_payload = dict(target or {})
        allow_capability_expansion = bool(
            target_payload.get("allow_capability_expansion")
            or target_payload.get("capability_expansion_accepted")
        )
        requested_ref = str(
            version
            or target_payload.get("version")
            or target_payload.get("ref")
            or entry.get("latest_version")
            or entry.get("default_ref")
            or ""
        ).strip()
        resolved_entry, resolved_target = resolve_install_target(
            entry,
            requested_ref,
            repository_client=self._repository_client,
        )
        entry = resolved_entry
        selected_ref = resolved_target
        if not selected_ref:
            raise ValueError("registry entry has no latest_version/default_ref and repository latest release could not be resolved")
        if self._blocklist_policy is None:
            raise ValueError(
                f"Cannot install extension '{ext_id}': blocklist policy is unavailable. "
                "Ensure extension registry services are available before installing extensions."
            )
        blocklist = self._blocklist_match_for_entry(entry, version=selected_ref, ref=selected_ref)
        if blocklist.get("matched"):
            reason = str(blocklist.get("reason") or "Extension is blocked by emergency policy.")
            raise ValueError(f"Extension '{ext_id}' is blocked by emergency blocklist: {reason}")
        storage_version = install_storage_segment(selected_ref)
        if not storage_version:
            raise ValueError("extension version/ref must be a safe path segment")
        target_dir = self._installed_dir / ext_id / storage_version
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{ext_id}-{storage_version}-staging-",
                dir=str(target_dir.parent),
            )
        )
        backup_dir: Path | None = None
        existing_record = next((record for record in self._repo.list_records() if record.id == ext_id and record.installed), None)
        try:
            self._install_entry_payload(entry, staging_dir, selected_ref=selected_ref)
            manifest = load_manifest_from_dir(staging_dir)
            validate_install_manifest(entry, manifest, selected_ref)
            if manifest.backend is None:
                raise ValueError("manifest backend is required")
            expansion = capability_expansion(
                existing_record,
                dict(getattr(manifest, "capabilities", {}) or {}),
                installed_capabilities_fn=self._installed_capabilities,
            )
            high_risk_expansion = [
                item for item in expansion if item.get("risk") in {"high", "critical"} or item.get("requires_user_consent")
            ]
            if high_risk_expansion and not allow_capability_expansion:
                names = ", ".join(item["id"] for item in high_risk_expansion[:8])
                raise ValueError(f"Extension update adds high-risk capabilities requiring consent: {names}")
            audit_extension_or_raise(staging_dir, manifest=manifest, entrypoint=manifest.backend.entrypoint)
            if target_dir.exists():
                backup_dir = target_dir.with_name(f"{target_dir.name}.previous-{_utc_now().replace(':', '')}")
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                target_dir.rename(backup_dir)
            shutil.move(str(staging_dir), str(target_dir))
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            if backup_dir is not None and backup_dir.exists() and not target_dir.exists():
                shutil.move(str(backup_dir), str(target_dir))
            raise
        finally:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
        records = [r for r in self._repo.list_records() if r.id != ext_id]
        provenance = install_provenance(entry, selected_ref, storage_version=storage_version)
        security_scan = {
            "status": "passed",
            "scanner": "chironai_static_audit",
            "scanned_at": _utc_now(),
            "findings": [],
        }
        records.append(
            InstalledExtensionRecord(
                id=ext_id,
                version=storage_version,
                enabled=True,
                installed=True,
                source={
                    k: v
                    for k, v in entry.items()
                    if k in {"repository", "repo_url", "source_path", "archive_url", "default_ref"}
                },
                title=str(entry.get("title") or ext_id),
                description=str(entry.get("description") or ""),
                icon=str(entry.get("icon") or ""),
                restart_required=True,
                restart_scope=RESTART_SCOPE_PROVIDER_REGISTRY,
                provenance=provenance,
                security_scan=security_scan,
                capabilities=dict(getattr(manifest, "capabilities", {}) or {}),
                blocked_reason="",
            )
        )
        self._repo.save_records(records)
        reload_status, reload_error = self._reload_runtime_after_state_change()
        return {
            "id": ext_id,
            "version": storage_version,
            "selected_ref": selected_ref,
            "restart_required": reload_status != "reloaded",
            "restart_scope": "none" if reload_status == "reloaded" else RESTART_SCOPE_PROVIDER_REGISTRY,
            "reload_status": reload_status,
            "status": "installed",
            "capability_expansion": expansion if existing_record is not None else [],
            **({"reload_error": reload_error} if reload_error else {}),
        }

    def _reload_runtime_after_state_change(self) -> tuple[str, str]:
        try:
            self.bootstrap_runtime()
        except Exception as e:
            return "failed", f"{type(e).__name__}: {e}"
        return "reloaded", ""

    def _installed_capabilities(self, record: InstalledExtensionRecord) -> dict[str, Any]:
        if record.capabilities:
            return dict(record.capabilities)
        source_dir = self._installed_dir / record.id / record.version
        if not source_dir.is_dir():
            return {}
        try:
            manifest = load_manifest_from_dir(source_dir)
        except Exception:
            return {}
        return dict(getattr(manifest, "capabilities", {}) or {})

    def _install_entry_payload(self, entry: dict[str, Any], target_dir: Path, *, selected_ref: str = "") -> None:
        source_path = str(entry.get("source_path") or "").strip()
        archive_url = str(entry.get("archive_url") or "").strip()
        repo_url = str(entry.get("repository") or entry.get("repo_url") or "").strip()
        expected_digest = str(entry.get("digest") or "").strip()
        if source_path:
            src = Path(source_path)
            src = (self._project_root / src).resolve() if not src.is_absolute() else src.resolve()
            # Guard against path traversal: source must stay inside project root.
            project_root_resolved = self._project_root.resolve()
            try:
                src.relative_to(project_root_resolved)
            except ValueError:
                raise ValueError(
                    f"source_path must be within project root, got: {source_path!r}"
                )
            if not src.is_dir():
                raise FileNotFoundError(f"extension source_path not found: {src}")
            shutil.copytree(src, target_dir, dirs_exist_ok=True)
            return
        if archive_url:
            validate_archive_url(archive_url)
            self._download_zip_to_dir(archive_url, target_dir, expected_digest=expected_digest)
            return
        if repo_url and repo_url.endswith(".zip"):
            validate_archive_url(repo_url)
            self._download_zip_to_dir(repo_url, target_dir, expected_digest=expected_digest)
            return
        resolved_github_archive_url = github_archive_url(repo_url, selected_ref)
        if resolved_github_archive_url:
            validate_archive_url(resolved_github_archive_url)
            self._download_zip_to_dir(resolved_github_archive_url, target_dir, expected_digest=expected_digest)
            return
        raise ValueError("registry entry must define source_path or archive_url/repo_url zip")

    def _download_zip_to_dir(self, url: str, target_dir: Path, *, expected_digest: str = "") -> None:
        download_extension_zip_to_dir(url, target_dir, expected_digest=expected_digest)

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
        reload_status, reload_error = self._reload_runtime_after_state_change()
        return {
            "id": result.id,
            "version": result.version,
            "enabled": result.enabled,
            "restart_required": reload_status != "reloaded",
            "restart_scope": "none" if reload_status == "reloaded" else result.restart_scope or RESTART_SCOPE_PROVIDER_REGISTRY,
            "reload_status": reload_status,
            **({"reload_error": reload_error} if reload_error else {}),
        }

    def enable(self, extension_id: str) -> dict[str, Any]:
        target = next((record for record in self._repo.list_records() if record.id == extension_id and record.installed), None)
        if target is not None:
            if self._blocklist_policy is None:
                raise ValueError(
                    f"Cannot enable extension '{extension_id}': blocklist policy is unavailable."
                )
            match = self._blocklist_match_for_record(target)
            if match.get("matched"):
                reason = str(match.get("reason") or "Extension is blocked by emergency policy.")
                raise ValueError(f"Extension '{extension_id}' is blocked by emergency blocklist: {reason}")
            # Reject re-enabling extensions that failed a non-blocklist security audit.
            if str((target.security_scan or {}).get("status") or "") == "blocked":
                findings = list((target.security_scan or {}).get("findings") or [])
                detail = findings[0].get("message") if findings else "security audit failed"
                raise ValueError(
                    f"Extension '{extension_id}' cannot be enabled: it was blocked by security scan ({detail}). "
                    "Remove and reinstall after the security issue is resolved."
                )
        return self._rewrite_record(
            extension_id,
            lambda r: InstalledExtensionRecord(
                **{
                    **r.__dict__,
                    "enabled": True,
                    "restart_required": True,
                    "restart_scope": RESTART_SCOPE_PROVIDER_REGISTRY,
                }
            ),
        )

    def disable(self, extension_id: str) -> dict[str, Any]:
        return self._rewrite_record(
            extension_id,
            lambda r: InstalledExtensionRecord(
                **{
                    **r.__dict__,
                    "enabled": False,
                    "restart_required": True,
                    "restart_scope": RESTART_SCOPE_PROVIDER_REGISTRY,
                }
            ),
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
        with self._lock:
            loaded_snapshot = list(self._loaded)
        for item in loaded_snapshot:
            if item.manifest.id == ext_id:
                close = getattr(item.provider, "close", None)
                if callable(close):
                    with contextlib.suppress(Exception):
                        close()
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
            restart_scope=RESTART_SCOPE_PROVIDER_REGISTRY,
            provenance=dict(target.provenance or {}),
            security_scan=dict(target.security_scan or {}),
            blocked_reason=target.blocked_reason,
        )
        self._repo.save_records([r for r in records if r.id != ext_id] + [tombstone])
        reload_status, reload_error = self._reload_runtime_after_state_change()
        return {
            "id": ext_id,
            "removed": True,
            "restart_required": reload_status != "reloaded",
            "restart_scope": "none" if reload_status == "reloaded" else RESTART_SCOPE_PROVIDER_REGISTRY,
            "reload_status": reload_status,
            **({"reload_error": reload_error} if reload_error else {}),
        }
