"""Extension tab UI orchestration helpers for ExtensionManager."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from llm_interactor.discovery import LoadedExtension
from llm_interactor.manager_install_helpers import utc_now_iso
from llm_interactor.runtime import LLMRuntime

# Keys in a tab payload that the extension must not override.  Authoritative
# values come from the manifest; extension code cannot spoof its own identity.
PROTECTED_TAB_PAYLOAD_KEYS: frozenset[str] = frozenset({"extension_id", "title", "icon", "icon_url"})
EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC = 2.0
EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC = 12.0


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


def tab_load_state(
    tab_cache: dict[str, ExtensionTabCacheEntry],
    lock: threading.RLock,
    extension_id: str,
    entry: ExtensionTabCacheEntry | None = None,
) -> dict[str, Any]:
    if entry is None:
        with lock:
            entry = tab_cache.get(extension_id)
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


def mark_tab_cache_stale_entries(tab_cache: dict[str, ExtensionTabCacheEntry]) -> None:
    for entry in tab_cache.values():
        if entry.status == "ready":
            entry.status = "stale"
            entry.error = ""


def invalidate_extension_tab_cache_entries(
    tab_cache: dict[str, ExtensionTabCacheEntry],
    extension_id: str | None = None,
) -> None:
    if extension_id:
        entry = tab_cache.get(extension_id)
        if entry is None:
            return
        if entry.payload or entry.descriptor:
            entry.status = "stale"
            entry.error = ""
        else:
            tab_cache.pop(extension_id, None)
        return
    for entry in tab_cache.values():
        if entry.payload or entry.descriptor:
            entry.status = "stale"
            entry.error = ""
    stale_ids = [
        ext_id
        for ext_id, entry in tab_cache.items()
        if not entry.payload and not entry.descriptor and entry.status != "refreshing"
    ]
    for ext_id in stale_ids:
        tab_cache.pop(ext_id, None)


def call_extension_ui_method(item: LoadedExtension, label: str, fn: Any, timeout_sec: float) -> Any:
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


def extension_descriptor_row(
    item: LoadedExtension,
    raw: dict[str, Any],
    *,
    asset_url: Any,
) -> dict[str, Any]:
    tab_id = str(raw.get("id") or "").strip() or item.manifest.id
    title = str(raw.get("title") or item.manifest.title).strip() or item.manifest.title
    icon = str(raw.get("icon") or item.manifest.icon or "")
    return {
        "id": tab_id,
        "extension_id": item.manifest.id,
        "title": title,
        "icon": icon,
        "icon_url": str(raw.get("icon_url") or "") or asset_url(item.manifest.id, icon),
        "description": str(raw.get("description") or item.manifest.description or ""),
        "frame": dict(raw.get("frame") or {}) if isinstance(raw.get("frame"), dict) else {},
        "order": int(raw.get("order") or 0),
        "status": dict(raw.get("status") or {}) if isinstance(raw.get("status"), dict) else None,
    }


def build_extension_descriptor(
    item: LoadedExtension,
    runtime: LLMRuntime | None,
    *,
    asset_url: Any,
) -> dict[str, Any] | None:
    fn = getattr(item.provider, "get_tab_descriptor", None)
    if not callable(fn):
        return None
    try:
        raw = call_extension_ui_method(
            item,
            "tab descriptor",
            lambda fn=fn: fn(runtime=runtime),
            EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC,
        )
    except TypeError:
        raw = call_extension_ui_method(
            item,
            "tab descriptor",
            lambda fn=fn: fn(),
            EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC,
        )
    if not isinstance(raw, dict):
        return None
    return extension_descriptor_row(item, raw, asset_url=asset_url)


def failed_tab_row(item: LoadedExtension, error: Exception, *, asset_url: Any) -> dict[str, Any]:
    sandbox_status = str(getattr(item.provider, "sandbox_status", "") or "failed")
    sandbox_error = str(getattr(item.provider, "sandbox_error", "") or f"{type(error).__name__}: {error}")
    return {
        "id": item.manifest.id,
        "extension_id": item.manifest.id,
        "title": item.manifest.title,
        "icon": item.manifest.icon,
        "icon_url": asset_url(item.manifest.id, item.manifest.icon),
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


def loaded_tab_status_overlay(item: LoadedExtension) -> dict[str, Any] | None:
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


def failed_tab_payload(item: LoadedExtension | None, error: Exception, *, asset_url: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    message = f"{type(error).__name__}: {error}"
    return {
        "extension_id": item.manifest.id,
        "title": item.manifest.title,
        "icon": item.manifest.icon,
        "icon_url": asset_url(item.manifest.id, item.manifest.icon),
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


def timeout_tab_payload(item: LoadedExtension, error: TimeoutError, *, asset_url: Any) -> dict[str, Any]:
    message = str(error)
    return {
        "extension_id": item.manifest.id,
        "title": item.manifest.title,
        "icon": item.manifest.icon,
        "icon_url": asset_url(item.manifest.id, item.manifest.icon),
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


def build_extension_tab_payload(
    item: LoadedExtension,
    runtime: LLMRuntime | None,
    *,
    asset_url: Any,
) -> dict[str, Any]:
    fn = getattr(item.provider, "get_tab_payload", None)
    if not callable(fn):
        return {
            "extension_id": item.manifest.id,
            "title": item.manifest.title,
            "icon": item.manifest.icon,
            "schema": dict(item.manifest.ui_schema or {}),
        }
    try:
        payload = call_extension_ui_method(
            item,
            "tab payload",
            lambda fn=fn: fn(runtime=runtime),
            EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC,
        )
    except TypeError:
        payload = call_extension_ui_method(
            item,
            "tab payload",
            lambda fn=fn: fn(),
            EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC,
        )
    if not isinstance(payload, dict):
        raise ValueError(f"Extension '{item.manifest.id}' returned invalid tab payload")
    safe_payload = {k: v for k, v in payload.items() if k not in PROTECTED_TAB_PAYLOAD_KEYS}
    return {
        "extension_id": item.manifest.id,
        "title": item.manifest.title,
        "icon": item.manifest.icon,
        "icon_url": asset_url(item.manifest.id, item.manifest.icon),
        **safe_payload,
    }


class ExtensionTabMixin:
    """Extension tab cache and UI orchestration mixed into ExtensionManager."""

    _tab_cache: dict[str, ExtensionTabCacheEntry]
    _tab_cache_generation: int
    _lock: threading.RLock

    def _tab_load_state(self, extension_id: str, entry: ExtensionTabCacheEntry | None = None) -> dict[str, Any]:
        return tab_load_state(self._tab_cache, self._lock, extension_id, entry)

    def _mark_tab_cache_stale(self) -> None:
        with self._lock:
            self._tab_cache_generation += 1
            mark_tab_cache_stale_entries(self._tab_cache)

    def invalidate_extension_tab_cache(self, extension_id: str | None = None) -> None:
        with self._lock:
            self._tab_cache_generation += 1
            invalidate_extension_tab_cache_entries(self._tab_cache, extension_id)

    def _call_extension_ui_method(self, item: LoadedExtension, label: str, fn: Any, timeout_sec: float) -> Any:
        return call_extension_ui_method(item, label, fn, timeout_sec)

    def _extension_descriptor_row(self, item: LoadedExtension, raw: dict[str, Any]) -> dict[str, Any]:
        return extension_descriptor_row(item, raw, asset_url=self._asset_url)

    def _build_extension_descriptor(self, item: LoadedExtension, runtime: LLMRuntime | None) -> dict[str, Any] | None:
        return build_extension_descriptor(item, runtime, asset_url=self._asset_url)

    def _failed_tab_row(self, item: LoadedExtension, error: Exception) -> dict[str, Any]:
        return failed_tab_row(item, error, asset_url=self._asset_url)

    def _loaded_tab_status_overlay(self, item: LoadedExtension) -> dict[str, Any] | None:
        return loaded_tab_status_overlay(item)

    def _failed_tab_payload(self, item: LoadedExtension | None, error: Exception) -> dict[str, Any] | None:
        return failed_tab_payload(item, error, asset_url=self._asset_url)

    def _timeout_tab_payload(self, item: LoadedExtension, error: TimeoutError) -> dict[str, Any]:
        return timeout_tab_payload(item, error, asset_url=self._asset_url)

    def _build_extension_tab_payload(self, item: LoadedExtension, runtime: LLMRuntime | None = None) -> dict[str, Any]:
        return build_extension_tab_payload(item, runtime, asset_url=self._asset_url)

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
            started_at = utc_now_iso()
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
        finished_at = utc_now_iso()
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
