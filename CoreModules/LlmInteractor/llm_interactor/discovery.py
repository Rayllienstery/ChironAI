"""Manifest scanning and provider factory loading."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from chironai_security import (
    ExtensionSecurityError,
    audit_extension,
    audit_extension_or_raise,
    format_blocking_error,
)
from llm_interactor.contracts import LLMProvider, ProviderHostContext
from llm_interactor.manifest import ExtensionManifest, manifest_from_dict


MANIFEST_FILENAME = "chironai-extension.json"


@dataclass(frozen=True)
class LoadedExtension:
    manifest: ExtensionManifest
    source_dir: Path
    provider: LLMProvider
    sandboxed: bool = False
    sandbox_status: str = ""
    sandbox_error: str = ""


@dataclass(frozen=True)
class FailedExtension:
    extension_id: str
    source_dir: Path
    error: str
    manifest: ExtensionManifest | None = None
    security_findings: list[dict[str, object]] = field(default_factory=list)
    sandbox_status: str = ""
    sandbox_error: str = ""


@dataclass
class ExtensionLoadReport:
    loaded: list[LoadedExtension] = field(default_factory=list)
    failed: list[FailedExtension] = field(default_factory=list)


def load_manifest_from_dir(source_dir: Path) -> ExtensionManifest:
    path = source_dir / MANIFEST_FILENAME
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest JSON must be an object")
    return manifest_from_dict(raw)


def _backend_source_paths(source_dir: Path, entrypoint: str) -> list[Path]:
    from chironai_security.extension_audit import backend_source_paths

    return backend_source_paths(source_dir, entrypoint)


def validate_extension_backend_docker_policy(source_dir: Path, entrypoint: str) -> None:
    """Reject extension backends that bypass host_context.docker_runtime."""

    report = audit_extension(source_dir, entrypoint=entrypoint)
    docker_findings = [item for item in report.blocking_findings if item.code == "docker_contract_violation"]
    if docker_findings:
        raise ValueError(
            format_blocking_error(type(report)(source_dir=report.source_dir, findings=docker_findings))
        )


def _load_factory_from_entrypoint(source_dir: Path, entrypoint: str):
    from extensions_sandbox.loader import load_factory_from_entrypoint

    return load_factory_from_entrypoint(source_dir, entrypoint)


def load_extension_provider_in_process(
    source_dir: Path,
    *,
    manifest: ExtensionManifest,
    host_context: ProviderHostContext,
) -> LLMProvider:
    """Test/helper path for direct provider loading after security audit."""

    if manifest.backend is None:
        raise ValueError("manifest backend is required")
    factory = _load_factory_from_entrypoint(source_dir, manifest.backend.entrypoint)
    return factory(host_context, manifest)


def _load_one_extension(
    source_dir: Path,
    *,
    host_context: ProviderHostContext,
    enabled: set[str],
    use_sandbox: bool,
) -> LoadedExtension | FailedExtension | None:
    """Load one extension.

    Returns:
        LoadedExtension  – provider started successfully.
        FailedExtension  – startup error (security, init, etc.).
        None             – extension is not in the enabled set; skip silently.
    """
    try:
        manifest = load_manifest_from_dir(source_dir)
        if enabled and manifest.id not in enabled:
            return None  # disabled — skip without recording a failure
        if manifest.backend is None:
            raise ValueError("manifest backend is required")
        audit_extension_or_raise(source_dir, manifest=manifest, entrypoint=manifest.backend.entrypoint)
        if use_sandbox:
            from extensions_sandbox import start_sandboxed_extension_provider  # noqa: PLC0415

            provider = start_sandboxed_extension_provider(
                source_dir=source_dir,
                entrypoint=manifest.backend.entrypoint,
                manifest=manifest,
                host_context=host_context,
            )
            return LoadedExtension(
                manifest=manifest,
                source_dir=source_dir,
                provider=provider,
                sandboxed=True,
                sandbox_status=str(getattr(provider, "sandbox_status", "ready") or "ready"),
            )
        provider = load_extension_provider_in_process(
            source_dir,
            manifest=manifest,
            host_context=host_context,
        )
        return LoadedExtension(manifest=manifest, source_dir=source_dir, provider=provider)
    except Exception as e:
        ext_id = source_dir.name
        manifest_for_failed: ExtensionManifest | None = None
        try:
            manifest_for_failed = load_manifest_from_dir(source_dir)
            ext_id = manifest_for_failed.id
        except Exception:
            pass
        security_findings: list[dict[str, object]] = []
        if isinstance(e, ExtensionSecurityError):
            security_findings = [item.to_dict() for item in e.report.findings]
        sandbox_status = str(getattr(e, "status", "") or "")
        return FailedExtension(
            extension_id=ext_id,
            source_dir=source_dir,
            error=f"{type(e).__name__}: {e}",
            manifest=manifest_for_failed,
            security_findings=security_findings,
            sandbox_status=sandbox_status,
            sandbox_error=f"{type(e).__name__}: {e}" if not security_findings else "",
        )


def discover_extensions(
    source_dirs: list[Path],
    *,
    host_context: ProviderHostContext,
    enabled_extension_ids: set[str] | None = None,
    use_sandbox: bool = True,
) -> ExtensionLoadReport:
    """Discover and load extensions, starting sandbox workers in parallel.

    Each sandbox worker startup blocks for its initialization handshake
    (up to 8 s per extension).  Running them concurrently cuts the total
    wait from O(n × startup_time) down to O(max(startup_time)).
    """
    report = ExtensionLoadReport()
    enabled = enabled_extension_ids or set()

    valid_dirs = [d for d in source_dirs if d.is_dir()]
    if not valid_dirs:
        return report

    # Parallelise sandbox startup: each ExtensionWorkerClient.__init__ blocks
    # on an 8-second initialize handshake; running them concurrently caps the
    # total wait at the slowest single extension instead of the sum.
    max_workers = max(1, len(valid_dirs))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ext-discovery") as pool:
        futures = {
            pool.submit(
                _load_one_extension,
                source_dir,
                host_context=host_context,
                enabled=enabled,
                use_sandbox=use_sandbox,
            ): source_dir
            for source_dir in valid_dirs
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                source_dir = futures[future]
                report.failed.append(
                    FailedExtension(
                        extension_id=source_dir.name,
                        source_dir=source_dir,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
                continue
            if result is None:
                continue  # extension was skipped (not in enabled set)
            if isinstance(result, LoadedExtension):
                report.loaded.append(result)
            else:
                report.failed.append(result)

    return report
