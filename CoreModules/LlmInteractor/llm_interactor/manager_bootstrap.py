"""Runtime bootstrap orchestration for extension discovery and provider registration."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from llm_interactor.contracts import ProviderHostContext
from llm_interactor.discovery import FailedExtension, LoadedExtension, discover_extensions
from llm_interactor.install_state import InstalledExtensionRecord
from llm_interactor.manifest import EXTENSION_TYPE_LLM_PROVIDER
from llm_interactor.runtime import LLMRuntime, ProviderRegistry


@dataclass(frozen=True)
class RuntimeBootstrap:
    runtime: LLMRuntime
    registry: ProviderRegistry
    loaded: list[LoadedExtension]
    failed: list[FailedExtension]


def discover_runtime_extensions(
    *,
    source_dirs: list[Path],
    host_context: ProviderHostContext,
    enabled_extension_ids: set[str],
    use_sandbox: bool,
    default_provider_id: str | None,
    on_security_blocked: Callable[[list[FailedExtension]], None],
) -> RuntimeBootstrap:
    report = discover_extensions(
        source_dirs,
        host_context=host_context,
        enabled_extension_ids=enabled_extension_ids,
        use_sandbox=use_sandbox,
    )
    on_security_blocked(report.failed)
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
                    sandbox_error=str(
                        getattr(loaded.provider, "sandbox_error", "") or f"{type(e).__name__}: {e}"
                    ),
                )
            )
    runtime = LLMRuntime(registry, default_provider_id=default_provider_id)
    return RuntimeBootstrap(
        runtime=runtime,
        registry=registry,
        loaded=list(report.loaded),
        failed=list(failed),
    )


def record_bootstrap_timing(
    *,
    bootstrap_start: float,
    bundled_start: float,
    discover_start: float,
    bootstrap: RuntimeBootstrap,
    source_dir_count: int,
    bundled_ms: float,
    discover_ms: float,
    bootstrap_total_ms: float,
) -> None:
    try:
        from api.http.startup_timing import process_start_offset_ms, record_phase
    except Exception:
        return
    ext_steps = []
    for loaded in bootstrap.loaded:
        timing = getattr(loaded, "startup_timing", None) or {}
        ext_steps.append(
            {
                "id": f"ext_{loaded.manifest.id}",
                "label": loaded.manifest.title or loaded.manifest.id,
                "description": f"v{loaded.manifest.version} — sandbox worker started",
                "start_offset_ms": process_start_offset_ms(discover_start),
                "duration_ms": round(float(timing.get("startup_ms", 0)), 1),
                "status": "ok",
            }
        )
    for failed in bootstrap.failed:
        ext_steps.append(
            {
                "id": f"ext_{failed.extension_id}",
                "label": getattr(failed.manifest, "title", None) or failed.extension_id
                if failed.manifest
                else failed.extension_id,
                "description": f"Failed: {failed.error[:120]}",
                "start_offset_ms": process_start_offset_ms(discover_start),
                "duration_ms": 0.0,
                "status": "failed",
            }
        )
    record_phase(
        phase_id="extensions_runtime",
        label="Extensions Runtime",
        description=(
            f"Background bootstrap: {len(bootstrap.loaded)} loaded, "
            f"{len(bootstrap.failed)} failed"
        ),
        start_offset_ms=process_start_offset_ms(bootstrap_start),
        duration_ms=bootstrap_total_ms,
        status="ok" if not bootstrap.failed else "failed",
        steps=[
            {
                "id": "bundled_install",
                "label": "Bundled Extensions Install",
                "description": "Copy bundled extensions to installed dir, apply blocklist",
                "start_offset_ms": process_start_offset_ms(bundled_start),
                "duration_ms": round(bundled_ms, 1),
                "status": "ok",
            },
            {
                "id": "discovery",
                "label": "Extension Discovery",
                "description": f"Discover and start {source_dir_count} extension sandbox worker(s) in parallel",
                "start_offset_ms": process_start_offset_ms(discover_start),
                "duration_ms": round(discover_ms, 1),
                "status": "ok",
            },
            *ext_steps,
        ],
        metadata={
            "loaded_count": len(bootstrap.loaded),
            "failed_count": len(bootstrap.failed),
            "extension_ids": [item.manifest.id for item in bootstrap.loaded],
        },
    )


def prewarm_provider_rows_async(
    runtime: LLMRuntime,
    *,
    provider_rows_fn: Callable[[Any], list[dict[str, Any]]],
    cache_lock: threading.RLock,
    cache: list[dict[str, Any]],
) -> None:
    def _worker() -> None:
        try:
            rows = provider_rows_fn(runtime)
            with cache_lock:
                if not cache:
                    cache[:] = rows
        except Exception:
            pass

    threading.Thread(
        target=_worker,
        name="chironai-provider-rows-prewarm",
        daemon=True,
    ).start()


def source_dirs_for_records(
    records: list[InstalledExtensionRecord],
    installed_dir: Path,
) -> list[Path]:
    return [
        installed_dir / record.id / record.version
        for record in records
        if record.installed and record.enabled and (installed_dir / record.id / record.version).is_dir()
    ]
