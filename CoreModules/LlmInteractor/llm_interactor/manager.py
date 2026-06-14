"""High-level extension management for installation, loading, and diagnostics."""

from __future__ import annotations

import logging
import queue
import re
import shutil
import stat
import threading
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests

from chironai_security import audit_extension_or_raise
from llm_interactor.contracts import ProviderHostContext
from llm_interactor.discovery import FailedExtension, LoadedExtension, MANIFEST_FILENAME, discover_extensions, load_manifest_from_dir
from llm_interactor.install_state import ExtensionsRepository, InstalledExtensionRecord
from llm_interactor.manifest import EXTENSION_API_VERSION, EXTENSION_TYPE_LLM_PROVIDER
from llm_interactor.runtime import LLMRuntime, ProviderRegistry

_log = logging.getLogger(__name__)
_MAX_EXTENSION_ZIP_BYTES = 500 * 1024 * 1024  # 500 MB hard ceiling
_MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB after extraction
_MAX_EXTENSION_ZIP_ENTRY_COUNT = 5000
_MAX_EXTENSION_ZIP_COMPRESSION_RATIO = 100.0

try:
    from extensions_backend import ExtensionBlocklistPolicy, ExtensionRegistryClient, GitHubExtensionRepositoryClient
except Exception as _ext_backend_import_error:  # pragma: no cover - optional module path during migration
    _log.warning(
        "extensions_backend module unavailable — blocklist enforcement and GitHub metadata are DISABLED: %s",
        _ext_backend_import_error,
    )
    ExtensionBlocklistPolicy = None  # type: ignore[assignment,misc]
    ExtensionRegistryClient = None  # type: ignore[assignment,misc]
    GitHubExtensionRepositoryClient = None  # type: ignore[assignment,misc]


DEFAULT_BUNDLED_DIR = "extensions/bundled"
DEFAULT_INSTALLED_DIR = "logs/extensions/installed"
RESTART_SCOPE_PROVIDER_REGISTRY = "provider_registry"
_SEMVERISH_RE = re.compile(r"^v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?$")

# Keys in a tab payload that the extension must not override.  Authoritative
# values come from the manifest; extension code cannot spoof its own identity.
_PROTECTED_TAB_PAYLOAD_KEYS: frozenset[str] = frozenset({"extension_id", "title", "icon", "icon_url"})
_EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC = 2.0
_EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC = 12.0

# Trusted hostnames for extension archive downloads.
# Only these domains may serve .zip archives; all other URLs are rejected to
# prevent SSRF attacks against internal services.
_TRUSTED_ARCHIVE_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",  # GitHub release asset CDN
        "codeload.github.com",            # GitHub archive download service
        "raw.githubusercontent.com",
    }
)

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


@dataclass(frozen=True)
class RuntimeBootstrap:
    runtime: LLMRuntime
    registry: ProviderRegistry
    loaded: list[LoadedExtension]
    failed: list[FailedExtension]


@dataclass
class ExtensionTabCacheEntry:
    status: str = "missing"
    descriptor: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: float | None = None
    cached_at: str = ""
    job_id: str = ""
    generation: int = 0
    phases: dict[str, str] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _github_archive_url(repository: str, ref: str) -> str:
    repo = str(repository or "").strip()
    selected_ref = str(ref or "").strip()
    if not repo or not selected_ref:
        return ""
    parsed = urlparse(repo)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        return ""
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return ""
    owner = quote(parts[0], safe="")
    name = quote(parts[1].removesuffix(".git"), safe="")
    safe_ref = quote(selected_ref, safe="")
    return f"https://github.com/{owner}/{name}/archive/{safe_ref}.zip"


def _github_raw_asset_url(repository: str, asset_path: str, *, ref: str = "HEAD") -> str:
    repo = str(repository or "").strip()
    rel = str(asset_path or "").strip().replace("\\", "/")
    selected_ref = str(ref or "").strip() or "HEAD"
    if not repo or not rel:
        return ""
    parsed_asset = urlparse(rel)
    if parsed_asset.scheme or parsed_asset.netloc or rel.startswith("/"):
        return ""
    parts = [part for part in rel.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    parsed_repo = urlparse(repo)
    if parsed_repo.scheme not in {"http", "https"} or parsed_repo.netloc.lower() != "github.com":
        return ""
    repo_parts = [part for part in parsed_repo.path.strip("/").split("/") if part]
    if len(repo_parts) < 2:
        return ""
    owner = quote(repo_parts[0], safe="")
    name = quote(repo_parts[1].removesuffix(".git"), safe="")
    safe_ref = quote(selected_ref, safe="")
    safe_path = "/".join(quote(part, safe="") for part in parts)
    return f"https://github.com/{owner}/{name}/raw/{safe_ref}/{safe_path}"


def _validate_archive_url(url: str) -> None:
    """Raise ValueError if *url* is not from a trusted archive host.

    This is the primary SSRF guard for extension downloads.  Only pre-approved
    CDN and source-hosting domains may serve extension archives; attempting to
    download from any other host (including ``localhost``, RFC-1918 addresses,
    or cloud metadata endpoints) raises immediately.
    """
    if not url:
        raise ValueError("archive URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"archive URL must use http or https scheme, got: {parsed.scheme!r}"
        )
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise ValueError("archive URL must have a valid hostname")
    if host not in _TRUSTED_ARCHIVE_HOSTS:
        raise ValueError(
            f"archive URL host {host!r} is not in the trusted hosts list; "
            "only github.com and its CDN domains are permitted"
        )


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def _path_contains_symlink(root: Path, candidate: Path) -> bool:
    """Return True if any existing component from root to candidate is a symlink."""
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _install_storage_segment(selected_ref: str) -> str:
    ref = str(selected_ref or "").strip()
    if not ref:
        return ""
    if "/" not in ref and "\\" not in ref and ref not in {".", ".."}:
        return ref
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", ref).strip(".-")[:48] or "ref"
    return f"{normalized}-{sha256(ref.encode('utf-8')).hexdigest()[:12]}"


class ExtensionManager:
    """Owns install state, discovery, and runtime bootstrap."""

    def __init__(
        self,
        *,
        project_root: Path,
        host_context: ProviderHostContext,
        settings_repo: Any,
        registry_client: Any | None = None,
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
        if registry_client is not None:
            self._registry_client = registry_client
        elif ExtensionRegistryClient is not None:
            self._registry_client = ExtensionRegistryClient(project_root=project_root)
        else:
            raise RuntimeError("ExtensionRegistryClient is unavailable")
        if repository_client is not None:
            self._repository_client = repository_client
        elif GitHubExtensionRepositoryClient is not None:
            self._repository_client = GitHubExtensionRepositoryClient()
        else:
            self._repository_client = None
        self._blocklist_policy = blocklist_policy or (ExtensionBlocklistPolicy(project_root=project_root) if ExtensionBlocklistPolicy else None)
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
                try:
                    close()
                except Exception:
                    pass

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
        try:
            self._registry_client.load_with_diagnostics()
        except Exception:
            pass

    def _prewarm_provider_rows(self, runtime: Any) -> None:
        """Populate _provider_rows_cache without blocking bootstrap or extension tab requests."""
        try:
            rows = self._provider_rows_from_runtime(runtime)
            with self._lock:
                # Only write if the cache is still empty (no concurrent update beat us).
                if not self._provider_rows_cache:
                    self._provider_rows_cache = rows
        except Exception:
            pass

    def _tab_load_state(self, extension_id: str, entry: ExtensionTabCacheEntry | None = None) -> dict[str, Any]:
        if entry is None:
            with self._lock:
                entry = self._tab_cache.get(extension_id)
        if entry is None:
            return {
                "status": "missing",
                "phases": {},
                "job_id": "",
                "started_at": "",
                "finished_at": "",
                "duration_ms": None,
                "cached_at": "",
                "error": "",
            }
        return {
            "status": entry.status,
            "phases": dict(entry.phases or {}),
            "job_id": entry.job_id,
            "started_at": entry.started_at,
            "finished_at": entry.finished_at,
            "duration_ms": entry.duration_ms,
            "cached_at": entry.cached_at,
            "error": entry.error,
        }

    def _mark_tab_cache_stale(self) -> None:
        with self._lock:
            self._tab_cache_generation += 1
            for entry in self._tab_cache.values():
                if entry.status == "ready":
                    entry.status = "stale"
                    entry.error = ""

    def invalidate_extension_tab_cache(self, extension_id: str | None = None) -> None:
        with self._lock:
            self._tab_cache_generation += 1
            if extension_id:
                entry = self._tab_cache.get(extension_id)
                if entry is None:
                    return
                if entry.payload or entry.descriptor:
                    entry.status = "stale"
                    entry.error = ""
                else:
                    self._tab_cache.pop(extension_id, None)
                return
            for entry in self._tab_cache.values():
                if entry.payload or entry.descriptor:
                    entry.status = "stale"
                    entry.error = ""
            stale_ids = [
                ext_id
                for ext_id, entry in self._tab_cache.items()
                if not entry.payload and not entry.descriptor and entry.status != "refreshing"
            ]
            for ext_id in stale_ids:
                self._tab_cache.pop(ext_id, None)

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

        try:
            from api.http.startup_timing import process_start_offset_ms, record_phase
            _timing_available = True
        except Exception:
            _timing_available = False

        with self._lock:
            self._runtime_status = "loading"
            self._runtime_error = ""

        _t_bundled = _time.perf_counter()
        self.ensure_bundled_installed()
        self._disable_blocklisted_records()
        _bundled_ms = (_time.perf_counter() - _t_bundled) * 1000

        records = [r for r in self._repo.list_records() if r.installed and r.enabled]
        source_dirs = [
            self._installed_dir / record.id / record.version
            for record in records
            if (self._installed_dir / record.id / record.version).is_dir()
        ]

        _t_discover = _time.perf_counter()
        report = discover_extensions(
            source_dirs,
            host_context=self._host_context,
            enabled_extension_ids={r.id for r in records},
            use_sandbox=self._use_sandbox,
        )
        _discover_ms = (_time.perf_counter() - _t_discover) * 1000

        self._disable_security_blocked_extensions(report.failed)
        registry = ProviderRegistry()
        failed = list(report.failed)
        for loaded in report.loaded:
            if loaded.manifest.type != EXTENSION_TYPE_LLM_PROVIDER:
                continue
            try:
                registry.register(loaded.provider)
            except Exception as e:
                close = getattr(loaded.provider, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
                failed.append(
                    FailedExtension(
                        extension_id=loaded.manifest.id,
                        source_dir=loaded.source_dir,
                        error=f"{type(e).__name__}: {e}",
                        manifest=loaded.manifest,
                        sandbox_status=str(getattr(loaded.provider, "sandbox_status", "") or ""),
                        sandbox_error=str(getattr(loaded.provider, "sandbox_error", "") or f"{type(e).__name__}: {e}"),
                    )
                )
        previous_loaded = self._loaded
        runtime = LLMRuntime(registry, default_provider_id=self._default_provider_id)
        bootstrap = RuntimeBootstrap(
            runtime=runtime,
            registry=registry,
            loaded=list(report.loaded),
            failed=list(failed),
        )
        with self._lock:
            self._shutdown_loaded_extensions(previous_loaded)
            # _loaded and _failed are written inside the lock so readers always
            # see a consistent pair of values; use bootstrap's already-copied lists.
            self._loaded = list(bootstrap.loaded)
            self._failed = list(bootstrap.failed)
            self._runtime = bootstrap.runtime
            self._registry = bootstrap.registry
            # Provider rows are computed lazily on first provider_catalog() call.
            # Pre-computing here would block extension workers (health_check +
            # list_models RPC calls) for up to ~18s per extension before _runtime
            # becomes ready, making extension tabs unresponsive.
            self._provider_rows_cache = []
            self._mark_tab_cache_stale()
            self._runtime_status = "ready"
            self._runtime_error = ""

        _bootstrap_total_ms = (_time.perf_counter() - _t_bootstrap_start) * 1000

        if _timing_available:
            ext_steps = []
            for loaded in report.loaded:
                timing = getattr(loaded, "startup_timing", None) or {}
                ext_steps.append({
                    "id": f"ext_{loaded.manifest.id}",
                    "label": loaded.manifest.title or loaded.manifest.id,
                    "description": f"v{loaded.manifest.version} — sandbox worker started",
                    "start_offset_ms": process_start_offset_ms(_t_discover),
                    "duration_ms": round(float(timing.get("startup_ms", 0)), 1),
                    "status": "ok",
                })
            for f in report.failed:
                ext_steps.append({
                    "id": f"ext_{f.extension_id}",
                    "label": getattr(f.manifest, "title", None) or f.extension_id if f.manifest else f.extension_id,
                    "description": f"Failed: {f.error[:120]}",
                    "start_offset_ms": process_start_offset_ms(_t_discover),
                    "duration_ms": 0.0,
                    "status": "failed",
                })
            record_phase(
                phase_id="extensions_runtime",
                label="Extensions Runtime",
                description=(
                    f"Background bootstrap: {len(report.loaded)} loaded, "
                    f"{len(report.failed)} failed"
                ),
                start_offset_ms=process_start_offset_ms(_t_bootstrap_start),
                duration_ms=_bootstrap_total_ms,
                status="ok" if not report.failed else "failed",
                steps=[
                    {
                        "id": "bundled_install",
                        "label": "Bundled Extensions Install",
                        "description": "Copy bundled extensions to installed dir, apply blocklist",
                        "start_offset_ms": process_start_offset_ms(_t_bundled),
                        "duration_ms": round(_bundled_ms, 1),
                        "status": "ok",
                    },
                    {
                        "id": "discovery",
                        "label": "Extension Discovery",
                        "description": f"Discover and start {len(source_dirs)} extension sandbox worker(s) in parallel",
                        "start_offset_ms": process_start_offset_ms(_t_discover),
                        "duration_ms": round(_discover_ms, 1),
                        "status": "ok",
                    },
                    *ext_steps,
                ],
                metadata={
                    "loaded_count": len(report.loaded),
                    "failed_count": len(report.failed),
                    "extension_ids": [e.manifest.id for e in report.loaded],
                },
            )

        # Pre-warm provider rows in a background thread so the LLM Proxy /
        # providers catalog is fast on first open without blocking tab loading.
        threading.Thread(
            target=self._prewarm_provider_rows,
            args=(runtime,),
            name="chironai-provider-rows-prewarm",
            daemon=True,
        ).start()
        for loaded in bootstrap.loaded:
            if loaded.manifest.type == EXTENSION_TYPE_LLM_PROVIDER:
                self.refresh_extension_tab(loaded.manifest.id, runtime=runtime)
        return bootstrap

    def _disable_security_blocked_extensions(self, failed: list[FailedExtension]) -> None:
        blocked = [item for item in failed if item.security_findings]
        if not blocked:
            return
        records = self._repo.list_records()
        by_id = {item.extension_id: item for item in blocked}
        changed = False
        next_records: list[InstalledExtensionRecord] = []
        for record in records:
            failed_item = by_id.get(record.id)
            if failed_item is None:
                next_records.append(record)
                continue
            scan = {
                "status": "blocked",
                "scanner": "chironai_static_audit",
                "scanned_at": _utc_now(),
                "findings": list(failed_item.security_findings),
            }
            next_records.append(
                InstalledExtensionRecord(
                    **{
                        **record.__dict__,
                        "enabled": False,
                        "restart_required": True,
                        "restart_scope": RESTART_SCOPE_PROVIDER_REGISTRY,
                        "security_scan": scan,
                        "blocked_reason": failed_item.error,
                    }
                )
            )
            changed = True
        if changed:
            self._repo.save_records(next_records)

    def _disable_blocklisted_records(self) -> None:
        records = self._repo.list_records()
        changed = False
        next_records: list[InstalledExtensionRecord] = []
        for record in records:
            if not record.installed:
                next_records.append(record)
                continue
            match = self._blocklist_match_for_record(record)
            if not match.get("matched"):
                next_records.append(record)
                continue
            scan = {
                "status": "blocked",
                "scanner": "chironai_blocklist",
                "scanned_at": _utc_now(),
                "findings": [
                    {
                        "severity": "critical",
                        "code": "EXTENSION_BLOCKLISTED",
                        "message": match.get("reason") or "Extension is blocked by emergency policy.",
                    }
                ],
            }
            next_records.append(
                InstalledExtensionRecord(
                    **{
                        **record.__dict__,
                        "enabled": False,
                        "restart_required": True,
                        "restart_scope": RESTART_SCOPE_PROVIDER_REGISTRY,
                        "security_scan": scan,
                        "blocked_reason": str(match.get("reason") or "Extension is blocked by emergency policy."),
                    }
                )
            )
            changed = True
        if changed:
            self._repo.save_records(next_records)

    def _publisher_name(self, value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("name") or value.get("id") or "").strip()
        return str(value or "").strip()

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
        if self._blocklist_policy is None:
            # Module-level import failed (migration scenario).  Log loudly so
            # operators notice, but allow bootstrap to continue — bricking an
            # existing deployment is worse than running without the emergency
            # blocklist in this transient state.  Remote installs and enables
            # are NOT in this code path (they use a stricter guard below).
            _log.error(
                "Blocklist policy is unavailable (extensions_backend missing?); "
                "extension '%s' will not be checked against emergency blocklist.",
                extension_id,
            )
            return {"matched": False, "reason": "", "source": "", "matched_on": ""}
        try:
            match = self._blocklist_policy.match(
                extension_id=extension_id,
                version=version,
                ref=ref,
                repository=repository or source_path,
                repository_id=repository_id,
                publisher=publisher,
            )
            return match.to_dict() if hasattr(match, "to_dict") else dict(match)
        except Exception as exc:
            _log.error(
                "Blocklist evaluation error for '%s' — treating as blocked (fail-closed): %s: %s",
                extension_id,
                type(exc).__name__,
                exc,
            )
            return {
                "matched": True,
                "reason": f"Blocklist evaluation error — cannot verify extension safety: {type(exc).__name__}",
                "source": "",
                "matched_on": "",
            }

    def _blocklist_match_for_entry(self, entry: dict[str, Any], *, version: str = "", ref: str = "") -> dict[str, Any]:
        return self._blocklist_match_for_values(
            extension_id=str(entry.get("id") or ""),
            version=version,
            ref=ref,
            repository=str(entry.get("repository") or entry.get("repo_url") or ""),
            repository_id=str(entry.get("repository_id") or ""),
            publisher=self._publisher_name(entry.get("publisher")),
            source_path=str(entry.get("source_path") or ""),
        )

    def _blocklist_match_for_record(self, record: InstalledExtensionRecord) -> dict[str, Any]:
        provenance = dict(record.provenance or {})
        source = dict(record.source or {})
        selected_ref = str(provenance.get("selected_ref") or provenance.get("selected_version") or record.version)
        return self._blocklist_match_for_values(
            extension_id=record.id,
            version=record.version,
            ref=selected_ref,
            repository=str(provenance.get("repository") or source.get("repository") or source.get("repo_url") or source.get("source_path") or ""),
            repository_id=str(provenance.get("repository_id") or ""),
            publisher="",
            source_path=str(source.get("source_path") or provenance.get("source_path") or ""),
        )

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
            if _path_contains_symlink(root, lexical_candidate):
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
        rows: list[dict[str, Any]] = []
        for entry in self._registry_client.load():
            out = dict(entry)
            if not str(out.get("icon_url") or "").strip():
                out["icon_url"] = _github_raw_asset_url(
                    str(out.get("repository") or out.get("repo_url") or ""),
                    str(out.get("icon") or ""),
                    ref=str(out.get("default_ref") or "HEAD"),
                )
            match = self._blocklist_match_for_entry(out)
            if match.get("matched"):
                out["blocklist"] = match
                out["visibility"] = "blocked"
            rows.append(out)
        return rows

    def registry_diagnostics(self) -> dict[str, Any]:
        loader = getattr(self._registry_client, "load_with_diagnostics", None)
        if callable(loader):
            result = loader()
            return {
                "registry_url": result.registry_url,
                "diagnostics": [item.to_dict() for item in result.diagnostics],
                "entries_count": len(result.entries),
            }
        return {
            "registry_url": getattr(self._registry_client, "registry_url", None),
            "diagnostics": [],
            "entries_count": len(self.registry_entries()),
        }

    def extension_details(self, extension_id: str, *, ref: str | None = None) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        entry = next((item for item in self.registry_entries() if str(item.get("id") or "").strip() == ext_id), None)
        if entry is None:
            raise ValueError(f"Extension '{ext_id}' not found in registry")
        repository = str(entry.get("repository") or entry.get("repo_url") or "").strip()
        details: dict[str, Any] = {
            "entry": dict(entry),
            "versions": [],
            "latest": {},
            "readme": {"extension_id": ext_id, "repository": repository, "markdown": "", "sanitized_html": ""},
            "publisher": dict(entry.get("publisher") or {}) if isinstance(entry.get("publisher"), dict) else {},
        }
        if not repository or self._repository_client is None:
            return details
        errors: list[str] = []
        try:
            latest = self._repository_client.latest_release(repository)
            details["latest"] = latest
        except Exception as e:
            latest = {}
            errors.append(f"latest_release: {type(e).__name__}: {e}")
        try:
            releases = self._repository_client.releases(repository)
        except Exception as e:
            releases = []
            errors.append(f"releases: {type(e).__name__}: {e}")
        try:
            tags = self._repository_client.tags(repository)
        except Exception as e:
            tags = []
            errors.append(f"tags: {type(e).__name__}: {e}")
        versions_by_ref: dict[str, dict[str, Any]] = {}
        for row in [latest, *releases, *tags]:
            if not isinstance(row, dict):
                continue
            key = str(row.get("ref") or row.get("version") or "").strip()
            if key and key not in versions_by_ref:
                versions_by_ref[key] = dict(row)
        details["versions"] = list(versions_by_ref.values())
        readme_ref = str(ref or (latest or {}).get("ref") or (latest or {}).get("version") or "").strip() or None
        try:
            readme = self._repository_client.readme(repository, ref=readme_ref)
            details["readme"] = {"extension_id": ext_id, **readme}
        except Exception as e:
            errors.append(f"readme: {type(e).__name__}: {e}")
            details["readme"] = {
                "extension_id": ext_id,
                "repository": repository,
                "ref": readme_ref or "",
                "markdown": "",
                "sanitized_html": "",
                "error": f"{type(e).__name__}: {e}",
            }
        if errors:
            details["warnings"] = errors
        return details

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
            sandbox = self._sandbox_diagnostics(loaded, failed)
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

    def _sandbox_diagnostics(
        self,
        loaded: LoadedExtension | None,
        failed: FailedExtension | None = None,
    ) -> dict[str, Any]:
        provider = loaded.provider if loaded is not None else None
        sandboxed = bool(getattr(loaded, "sandboxed", False)) if loaded is not None else bool(failed and failed.sandbox_status)
        sandbox_status = (
            str(getattr(provider, "sandbox_status", "") or getattr(loaded, "sandbox_status", ""))
            if loaded is not None
            else str(failed.sandbox_status if failed is not None else "")
        )
        sandbox_error = (
            str(
                getattr(provider, "sandbox_last_error", "")
                or getattr(provider, "sandbox_error", "")
                or getattr(loaded, "sandbox_error", "")
            )
            if loaded is not None
            else str(failed.sandbox_error if failed is not None else "")
        )
        sandbox_pid = getattr(provider, "sandbox_pid", None) if provider is not None else None
        sandbox_restart_count = int(getattr(provider, "sandbox_restart_count", 0) or 0) if provider is not None else 0
        sandbox_blocked = bool(getattr(provider, "sandbox_blocked", False)) if provider is not None else False
        manual_required = (
            bool(getattr(provider, "sandbox_manual_restart_required", False))
            if provider is not None
            else sandbox_status in {"blocked", "manual_stop"}
        )
        return {
            "sandboxed": sandboxed,
            "sandbox_pid": sandbox_pid,
            "sandbox_status": sandbox_status,
            "sandbox_error": sandbox_error,
            "sandbox_last_error": sandbox_error,
            "sandbox_restart_count": sandbox_restart_count,
            "sandbox_blocked": sandbox_blocked,
            "sandbox_manual_restart_required": manual_required,
            "sandbox_can_restart": bool(loaded is not None and sandboxed),
            "sandbox_can_kill": bool(loaded is not None and sandboxed and sandbox_pid is not None),
        }

    def _provider_rows_from_runtime(self, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        rt = runtime
        rows: list[dict[str, Any]] = []
        if rt is not None:
            healths = {}
            for provider in rt.registry.providers():
                try:
                    health = provider.health_check()
                    healths[health.provider_id] = health
                except Exception:
                    continue
            models_by_provider: dict[str, list[dict[str, Any]]] = {}
            descriptors = []
            for provider in rt.registry.providers():
                try:
                    desc = provider.describe()
                    descriptors.append(desc)
                    for model in provider.list_models():
                        models_by_provider.setdefault(model.provider_id, []).append(
                            {
                                "id": model.id,
                                "label": model.label,
                                "description": model.description,
                                "metadata": dict(model.metadata or {}),
                            }
                        )
                except Exception:
                    continue
            for desc in descriptors:
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
        with self._lock:
            snapshot = list(self._loaded)
        for item in snapshot:
            if item.manifest.id == ext_id:
                return item
        return None

    def _call_extension_ui_method(self, item: LoadedExtension, label: str, fn: Any, timeout_sec: float) -> Any:
        """Run extension UI hooks with a hard response budget."""
        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def _target() -> None:
            try:
                result_queue.put((True, fn()))
            except BaseException as exc:  # pragma: no cover - re-raised in caller thread
                result_queue.put((False, exc))

        thread = threading.Thread(
            target=_target,
            name=f"chironai-extension-ui-{item.manifest.id}-{label}",
            daemon=True,
        )
        thread.start()
        try:
            ok, value = result_queue.get(timeout=timeout_sec)
        except queue.Empty as exc:
            raise TimeoutError(
                f"Extension '{item.manifest.id}' {label} timed out after {timeout_sec:.1f}s"
            ) from exc
        if ok:
            return value
        raise value

    def _extension_descriptor_row(
        self,
        item: LoadedExtension,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        tab_id = str(raw.get("id") or "").strip() or item.manifest.id
        title = str(raw.get("title") or item.manifest.title).strip() or item.manifest.title
        icon = str(raw.get("icon") or item.manifest.icon or "")
        return {
            "id": tab_id,
            "extension_id": item.manifest.id,
            "title": title,
            "icon": icon,
            "icon_url": str(raw.get("icon_url") or "") or self._asset_url(item.manifest.id, icon),
            "description": str(raw.get("description") or item.manifest.description or ""),
            "frame": dict(raw.get("frame") or {}) if isinstance(raw.get("frame"), dict) else {},
            "order": int(raw.get("order") or 0),
            "status": dict(raw.get("status") or {}) if isinstance(raw.get("status"), dict) else None,
        }

    def _build_extension_descriptor(self, item: LoadedExtension, runtime: LLMRuntime | None) -> dict[str, Any] | None:
        fn = getattr(item.provider, "get_tab_descriptor", None)
        if not callable(fn):
            return None
        try:
            raw = self._call_extension_ui_method(
                item,
                "tab descriptor",
                lambda fn=fn: fn(runtime=runtime),
                _EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC,
            )
        except TypeError:
            raw = self._call_extension_ui_method(
                item,
                "tab descriptor",
                lambda fn=fn: fn(),
                _EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC,
            )
        if not isinstance(raw, dict):
            return None
        return self._extension_descriptor_row(item, raw)

    def _manifest_for_extension(self, extension_id: str) -> tuple[InstalledExtensionRecord, Any] | None:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            return None
        for record, _source_dir, manifest in self._installed_manifest_rows(enabled_only=True):
            if str(getattr(manifest, "id", record.id)) == ext_id or record.id == ext_id:
                return record, manifest
        return None

    def _minimal_tab_payload(self, extension_id: str, *, entry: ExtensionTabCacheEntry | None = None) -> dict[str, Any]:
        item = self._find_loaded_extension(extension_id)
        manifest = item.manifest if item is not None else None
        record_manifest = None if manifest is not None else self._manifest_for_extension(extension_id)
        if manifest is None and record_manifest is not None:
            _record, manifest = record_manifest
        if manifest is None:
            raise ValueError(f"Extension '{extension_id}' is not loaded")
        icon = str(getattr(manifest, "icon", "") or "")
        return {
            "extension_id": str(getattr(manifest, "id", extension_id)),
            "title": str(getattr(manifest, "title", extension_id) or extension_id),
            "icon": icon,
            "icon_url": self._asset_url(str(getattr(manifest, "id", extension_id)), icon),
            "status": {
                "running": False,
                "tone": "loading",
                "message": "Extension tab payload is loading",
            },
            "schema": {"pages": []},
            "load_state": self._tab_load_state(extension_id, entry),
        }

    def refresh_extension_tab(
        self,
        extension_id: str,
        *,
        runtime: LLMRuntime | None = None,
    ) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        if runtime is None:
            runtime = self.runtime
        with self._lock:
            entry = self._tab_cache.get(ext_id)
            if entry is not None and entry.status == "refreshing":
                return {"job_id": entry.job_id, "load_state": self._tab_load_state(ext_id, entry)}
            if entry is None:
                entry = ExtensionTabCacheEntry()
                self._tab_cache[ext_id] = entry
            if runtime is None:
                entry.status = "missing"
                entry.error = "Extension runtime is still loading"
                return {"job_id": "", "load_state": self._tab_load_state(ext_id, entry)}
            self._tab_cache_generation += 1
            generation = self._tab_cache_generation
            job_id = uuid.uuid4().hex[:12]
            started_at = _utc_now()
            entry.status = "refreshing"
            entry.error = ""
            entry.started_at = started_at
            entry.finished_at = ""
            entry.duration_ms = None
            entry.job_id = job_id
            entry.generation = generation
            entry.phases = {"descriptor": "pending", "payload": "pending"}
        threading.Thread(
            target=self._refresh_extension_tab_worker,
            args=(ext_id, runtime, job_id, generation),
            name=f"chironai-extension-tab-refresh-{ext_id}",
            daemon=True,
        ).start()
        return {"job_id": job_id, "load_state": self._tab_load_state(ext_id)}

    def _refresh_extension_tab_worker(
        self,
        extension_id: str,
        runtime: LLMRuntime,
        job_id: str,
        generation: int,
    ) -> None:
        started = time.perf_counter()
        descriptor: dict[str, Any] | None = None
        payload: dict[str, Any] | None = None
        status = "ready"
        error = ""
        phases = {"descriptor": "pending", "payload": "pending"}
        try:
            item = self._find_loaded_extension(extension_id)
            if item is None:
                raise ValueError(f"Extension '{extension_id}' is not loaded")
            try:
                phases["descriptor"] = "refreshing"
                descriptor = self._build_extension_descriptor(item, runtime)
                phases["descriptor"] = "ready" if descriptor is not None else "skipped"
            except TimeoutError as exc:
                phases["descriptor"] = "timeout"
                status = "timeout"
                error = str(exc)
                descriptor = self._failed_tab_row(item, exc)
            except Exception as exc:
                phases["descriptor"] = "failed"
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
                descriptor = self._failed_tab_row(item, exc)
            phases["payload"] = "refreshing"
            payload = self._build_extension_tab_payload(item, runtime)
            phases["payload"] = "ready"
            if status not in {"failed", "timeout"}:
                status = "ready"
                error = ""
        except TimeoutError as exc:
            status = "timeout"
            error = str(exc)
            phases["payload"] = "timeout"
            payload = None
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            phases["payload"] = "failed"
            item = self._find_loaded_extension(extension_id)
            payload = self._failed_tab_payload(item, exc) if item is not None else None
        finished_at = _utc_now()
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        with self._lock:
            entry = self._tab_cache.get(extension_id)
            if entry is None or entry.job_id != job_id or entry.generation != generation:
                return
            entry.status = status
            entry.descriptor = descriptor or entry.descriptor
            entry.payload = payload or entry.payload
            entry.error = error
            entry.finished_at = finished_at
            entry.duration_ms = duration_ms
            entry.cached_at = finished_at if payload or descriptor else entry.cached_at
            entry.phases = phases

    def _failed_tab_row(self, item: LoadedExtension, error: Exception) -> dict[str, Any]:
        sandbox_status = str(getattr(item.provider, "sandbox_status", "") or "failed")
        sandbox_error = str(getattr(item.provider, "sandbox_error", "") or f"{type(error).__name__}: {error}")
        return {
            "id": item.manifest.id,
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
            "description": item.manifest.description,
            "frame": {},
            "order": 0,
            "status": {
                "runtime": sandbox_status,
                "tone": "warning" if sandbox_status == "manual_stop" else "error",
                "message": sandbox_error,
                "running": False,
            },
        }

    def _loaded_tab_status_overlay(self, item: LoadedExtension) -> dict[str, Any] | None:
        sandbox_status = str(getattr(item.provider, "sandbox_status", "") or "").strip()
        if not sandbox_status or sandbox_status == "ready":
            return None
        sandbox_error = str(getattr(item.provider, "sandbox_error", "") or "").strip()
        if not sandbox_error and sandbox_status == "manual_stop":
            sandbox_error = "Extension worker is stopped until manual restart"
        return {
            "runtime": sandbox_status,
            "tone": "warning" if sandbox_status == "manual_stop" else "error",
            "message": sandbox_error or sandbox_status,
            "running": False,
        }

    def _failed_tab_payload(self, item: LoadedExtension | None, error: Exception) -> dict[str, Any] | None:
        if item is None:
            return None
        message = f"{type(error).__name__}: {error}"
        return {
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
            "status": {
                "running": False,
                "tone": "error",
                "message": message,
            },
            "schema": {
                "pages": [
                    {
                        "id": "extension-error",
                        "title": item.manifest.title,
                        "sections": [
                            {
                                "id": "extension-error",
                                "title": "Extension runtime unavailable",
                                "components": [
                                    {
                                        "type": "text",
                                        "key": "extension_error",
                                        "label": "Error",
                                        "value": message,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    def _timeout_tab_payload(self, item: LoadedExtension, error: TimeoutError) -> dict[str, Any]:
        message = str(error)
        return {
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
            "status": {
                "running": False,
                "tone": "error",
                "message": message,
            },
            "schema": {
                "pages": [
                    {
                        "id": "extension-timeout",
                        "title": item.manifest.title,
                        "sections": [
                            {
                                "id": "extension-timeout",
                                "title": "Extension runtime unavailable",
                                "components": [
                                    {
                                        "type": "text",
                                        "key": "extension_timeout",
                                        "label": "Timeout",
                                        "value": message,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    def _build_extension_tab_payload(self, item: LoadedExtension, runtime: LLMRuntime | None = None) -> dict[str, Any]:
        fn = getattr(item.provider, "get_tab_payload", None)
        if not callable(fn):
            return {
                "extension_id": item.manifest.id,
                "title": item.manifest.title,
                "icon": item.manifest.icon,
                "schema": dict(item.manifest.ui_schema or {}),
            }
        try:
            payload = self._call_extension_ui_method(
                item,
                "tab payload",
                lambda fn=fn: fn(runtime=runtime),
                _EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC,
            )
        except TypeError:
            payload = self._call_extension_ui_method(
                item,
                "tab payload",
                lambda fn=fn: fn(),
                _EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC,
            )
        if not isinstance(payload, dict):
            raise ValueError(f"Extension '{extension_id}' returned invalid tab payload")
        # Strip keys that the extension must not override — extension_id, title,
        # icon, and icon_url are authoritative from the manifest, not the payload.
        safe_payload = {k: v for k, v in payload.items() if k not in _PROTECTED_TAB_PAYLOAD_KEYS}
        return {
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            "icon_url": self._asset_url(item.manifest.id, item.manifest.icon),
            **safe_payload,
        }

    def extension_tabs(self, *, runtime: LLMRuntime | None = None) -> list[dict[str, Any]]:
        if runtime is None:
            runtime = self.runtime
        out = self._manifest_tabs()
        by_extension_id = {str(row.get("extension_id") or row.get("id") or ""): dict(row) for row in out}
        with self._lock:
            loaded_snapshot = list(self._loaded)
            cache_snapshot = {k: v for k, v in self._tab_cache.items()}
        for item in loaded_snapshot:
            ext_id = item.manifest.id
            entry = cache_snapshot.get(ext_id)
            row = by_extension_id.get(ext_id)
            if row is None and callable(getattr(item.provider, "get_tab_descriptor", None)):
                row = {
                    "id": ext_id,
                    "extension_id": ext_id,
                    "title": item.manifest.title,
                    "icon": item.manifest.icon,
                    "icon_url": self._asset_url(ext_id, item.manifest.icon),
                    "description": item.manifest.description,
                    "frame": {},
                    "order": 0,
                    "status": {
                        "runtime": self.runtime_status,
                        "tone": "loading",
                        "message": "Extension descriptor is loading",
                        "running": False,
                    },
                }
            if row is None:
                continue
            status_overlay = self._loaded_tab_status_overlay(item)
            if status_overlay is not None:
                row["status"] = status_overlay
            if entry is not None and entry.descriptor:
                merged = {**row, **entry.descriptor}
                row = merged
            row["load_state"] = self._tab_load_state(ext_id, entry)
            by_extension_id[ext_id] = row
            if runtime is not None and (entry is None or entry.status in {"missing", "stale", "failed", "timeout"}):
                self.refresh_extension_tab(ext_id, runtime=runtime)
        out = list(by_extension_id.values())
        out.sort(key=lambda row: (int(row.get("order") or 0), str(row.get("title") or "").lower()))
        return out

    def extension_tab_payload(self, extension_id: str, *, runtime: LLMRuntime | None = None) -> dict[str, Any]:
        ext_id = str(extension_id or "").strip()
        if not ext_id:
            raise ValueError("extension_id is required")
        if runtime is None:
            runtime = self.runtime
        with self._lock:
            entry = self._tab_cache.get(ext_id)
        if entry is not None and entry.payload is not None:
            payload = dict(entry.payload)
            payload["load_state"] = self._tab_load_state(ext_id, entry)
            return payload
        if runtime is not None and (entry is None or entry.status == "missing"):
            self.refresh_extension_tab(ext_id, runtime=runtime)
            with self._lock:
                entry = self._tab_cache.get(ext_id)
        return self._minimal_tab_payload(ext_id, entry=entry)

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
            sandbox = self._sandbox_diagnostics(item)
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
            sandbox = self._sandbox_diagnostics(item)
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
            sandbox = self._sandbox_diagnostics(loaded)
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
                    **self._sandbox_diagnostics(None, item),
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
        resolved_entry, resolved_target = self._resolve_install_target(entry, requested_ref)
        entry = resolved_entry
        selected_ref = resolved_target
        if not selected_ref:
            raise ValueError("registry entry has no latest_version/default_ref and repository latest release could not be resolved")
        if self._blocklist_policy is None:
            raise ValueError(
                f"Cannot install extension '{ext_id}': blocklist policy is unavailable. "
                "Ensure extensions_backend is installed and operational before installing extensions."
            )
        blocklist = self._blocklist_match_for_entry(entry, version=selected_ref, ref=selected_ref)
        if blocklist.get("matched"):
            reason = str(blocklist.get("reason") or "Extension is blocked by emergency policy.")
            raise ValueError(f"Extension '{ext_id}' is blocked by emergency blocklist: {reason}")
        storage_version = _install_storage_segment(selected_ref)
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
            self._validate_install_manifest(entry, manifest, selected_ref)
            if manifest.backend is None:
                raise ValueError("manifest backend is required")
            expansion = self._capability_expansion(existing_record, dict(getattr(manifest, "capabilities", {}) or {}))
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
        provenance = self._install_provenance(entry, selected_ref, storage_version=storage_version)
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

    def _capability_expansion(self, existing: InstalledExtensionRecord | None, next_capabilities: dict[str, Any]) -> list[dict[str, Any]]:
        if existing is None:
            return []
        previous = self._installed_capabilities(existing)
        previous_ids = self._enabled_capability_ids(previous)
        next_ids = self._enabled_capability_ids(next_capabilities)
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

    def _enabled_capability_ids(self, capabilities: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        for key, value in dict(capabilities or {}).items():
            cap = str(key or "").strip()
            if not cap:
                continue
            if isinstance(value, dict):
                enabled = bool(value.get("enabled", True))
            else:
                enabled = bool(value)
            if enabled:
                out.add(cap)
        return out

    def _validate_install_manifest(self, entry: dict[str, Any], manifest: Any, target_version: str) -> None:
        expected_id = str(entry.get("id") or "").strip()
        if manifest.id != expected_id:
            raise ValueError(f"manifest id mismatch: expected '{expected_id}', got '{manifest.id}'")
        # For semver-shaped refs the manifest version must match exactly (modulo leading 'v').
        # For non-semver refs (branch names, commit SHAs) we still reject obviously wrong
        # versions: if the manifest declares a semver version it must not be empty.
        if _SEMVERISH_RE.match(target_version):
            if manifest.version.lstrip("v") != target_version.lstrip("v"):
                raise ValueError(f"manifest version mismatch: expected '{target_version}', got '{manifest.version}'")
        else:
            if not str(manifest.version or "").strip():
                raise ValueError(
                    f"manifest for extension '{expected_id}' installed from ref '{target_version}' "
                    "must declare a non-empty version"
                )
        self._validate_compatibility(dict(getattr(manifest, "compatibility", {}) or {}))
        registry_compat = entry.get("compatibility")
        if isinstance(registry_compat, dict):
            self._validate_compatibility(dict(registry_compat))

    def _validate_compatibility(self, compatibility: dict[str, Any]) -> None:
        api_version = str(compatibility.get("extension_api_version") or EXTENSION_API_VERSION).strip()
        if api_version != EXTENSION_API_VERSION:
            raise ValueError(f"unsupported extension_api_version: {api_version}")
        app = str(compatibility.get("app") or "chironai").strip().lower()
        if app not in {"chironai", "chiron ai"}:
            raise ValueError(f"unsupported extension app compatibility: {app}")

    def _resolve_install_target(self, entry: dict[str, Any], requested_ref: str) -> tuple[dict[str, Any], str]:
        resolved = dict(entry)
        repository = str(resolved.get("repository") or resolved.get("repo_url") or "").strip()
        if not repository or self._repository_client is None:
            return resolved, requested_ref
        if requested_ref:
            try:
                for version in self._repository_client.releases(repository):
                    ref = str(version.get("ref") or version.get("version") or "").strip()
                    if ref == requested_ref or ref.lstrip("v") == requested_ref.lstrip("v"):
                        return self._entry_with_version_payload(resolved, version), ref
            except Exception as exc:
                _log.warning(
                    "extension install: could not fetch releases for %s (ref=%s): %s: %s",
                    repository,
                    requested_ref,
                    type(exc).__name__,
                    exc,
                )
            return resolved, requested_ref
        latest = self._repository_client.latest_release(repository)
        latest_ref = str(latest.get("ref") or latest.get("version") or "").strip()
        return self._entry_with_version_payload(resolved, latest), latest_ref

    def _entry_with_version_payload(self, entry: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
        out = dict(entry)
        archive_url = str(version.get("archive_url") or "").strip()
        if archive_url:
            out["archive_url"] = archive_url
        for key in ("digest", "commit_sha", "provenance_level", "release_url", "target_kind"):
            if version.get(key):
                out[key] = version[key]
        return out

    def _install_provenance(self, entry: dict[str, Any], selected_ref: str, *, storage_version: str) -> dict[str, Any]:
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
            "installed_at": _utc_now(),
        }

    def _install_entry_payload(self, entry: dict[str, Any], target_dir: Path, *, selected_ref: str = "") -> None:
        source_path = str(entry.get("source_path") or "").strip()
        archive_url = str(entry.get("archive_url") or "").strip()
        repo_url = str(entry.get("repository") or entry.get("repo_url") or "").strip()
        expected_digest = str(entry.get("digest") or "").strip()
        if source_path:
            src = Path(source_path)
            if not src.is_absolute():
                src = (self._project_root / src).resolve()
            else:
                src = src.resolve()
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
            _validate_archive_url(archive_url)
            self._download_zip_to_dir(archive_url, target_dir, expected_digest=expected_digest)
            return
        if repo_url and repo_url.endswith(".zip"):
            _validate_archive_url(repo_url)
            self._download_zip_to_dir(repo_url, target_dir, expected_digest=expected_digest)
            return
        github_archive_url = _github_archive_url(repo_url, selected_ref)
        if github_archive_url:
            # _github_archive_url already restricts to github.com; still validate for defence-in-depth.
            _validate_archive_url(github_archive_url)
            self._download_zip_to_dir(github_archive_url, target_dir, expected_digest=expected_digest)
            return
        raise ValueError("registry entry must define source_path or archive_url/repo_url zip")

    def _download_zip_to_dir(self, url: str, target_dir: Path, *, expected_digest: str = "") -> None:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        hasher = sha256()
        total_bytes = 0
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp_path = Path(tmp.name)
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_EXTENSION_ZIP_BYTES:
                        raise ValueError(
                            f"extension archive exceeds maximum allowed size "
                            f"({_MAX_EXTENSION_ZIP_BYTES // (1024 * 1024)} MB): {url}"
                        )
                    hasher.update(chunk)
                    tmp.write(chunk)
            if expected_digest:
                actual_digest = hasher.hexdigest()
                clean_expected = expected_digest.removeprefix("sha256:")
                if actual_digest != clean_expected:
                    raise ValueError(
                        f"extension archive digest mismatch for {url}: "
                        f"expected sha256:{clean_expected}, got sha256:{actual_digest}"
                    )
            with zipfile.ZipFile(tmp_path) as zf:
                infos = [info for info in zf.infolist() if info.filename and not info.filename.endswith("/")]
                if len(infos) > _MAX_EXTENSION_ZIP_ENTRY_COUNT:
                    raise ValueError(
                        f"extension archive contains too many files "
                        f"({len(infos)} > {_MAX_EXTENSION_ZIP_ENTRY_COUNT})"
                    )
                uncompressed_total = 0
                names = [info.filename.replace("\\", "/") for info in infos]
                for info, name in zip(infos, names, strict=True):
                    if _zip_member_is_symlink(info):
                        raise ValueError(f"unsafe zip member is a symlink: {name}")
                    uncompressed_total += int(info.file_size or 0)
                    if uncompressed_total > _MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES:
                        raise ValueError(
                            f"extension archive expands beyond maximum allowed size "
                            f"({_MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)} MB): {url}"
                        )
                    if info.file_size and info.compress_size == 0:
                        raise ValueError(f"unsafe zip member has invalid compressed size: {name}")
                    if info.file_size and info.compress_size:
                        ratio = float(info.file_size) / float(info.compress_size)
                        if ratio > _MAX_EXTENSION_ZIP_COMPRESSION_RATIO:
                            raise ValueError(f"unsafe zip member compression ratio: {name}")
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
            if tmp_path is not None:
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
                    try:
                        close()
                    except Exception:
                        pass
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
