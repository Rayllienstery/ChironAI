"""Manifest scanning and provider factory loading."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
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


@dataclass(frozen=True)
class FailedExtension:
    extension_id: str
    source_dir: Path
    error: str
    manifest: ExtensionManifest | None = None
    security_findings: list[dict[str, object]] = field(default_factory=list)


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
    module_name, _, attr_name = entrypoint.partition(":")
    if not module_name or not attr_name:
        raise ValueError("backend.entrypoint must be 'module:callable'")
    module_rel = module_name.replace(".", "/")
    py_path = source_dir / f"{module_rel}.py"
    package_init = source_dir / module_rel / "__init__.py"
    if py_path.is_file():
        spec = importlib.util.spec_from_file_location(
            f"chironai_ext_{source_dir.name}_{module_name.replace('.', '_')}",
            py_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load module from {py_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    elif package_init.is_file():
        spec = importlib.util.spec_from_file_location(
            f"chironai_ext_{source_dir.name}_{module_name.replace('.', '_')}",
            package_init,
            submodule_search_locations=[str(package_init.parent)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load package from {package_init}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(module_name)
    factory = getattr(mod, attr_name, None)
    if factory is None:
        raise AttributeError(f"entrypoint callable not found: {entrypoint}")
    return factory


def discover_extensions(
    source_dirs: list[Path],
    *,
    host_context: ProviderHostContext,
    enabled_extension_ids: set[str] | None = None,
) -> ExtensionLoadReport:
    report = ExtensionLoadReport()
    enabled = enabled_extension_ids or set()
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        try:
            manifest = load_manifest_from_dir(source_dir)
            if enabled and manifest.id not in enabled:
                continue
            if manifest.backend is None:
                raise ValueError("manifest backend is required")
            audit_extension_or_raise(source_dir, manifest=manifest, entrypoint=manifest.backend.entrypoint)
            factory = _load_factory_from_entrypoint(source_dir, manifest.backend.entrypoint)
            provider = factory(host_context, manifest)
            report.loaded.append(LoadedExtension(manifest=manifest, source_dir=source_dir, provider=provider))
        except Exception as e:  # pragma: no cover - exercised via manager diagnostics
            ext_id = source_dir.name
            manifest = None
            try:
                manifest = load_manifest_from_dir(source_dir)
                ext_id = manifest.id
            except Exception:
                pass
            security_findings: list[dict[str, object]] = []
            if isinstance(e, ExtensionSecurityError):
                security_findings = [item.to_dict() for item in e.report.findings]
            report.failed.append(
                FailedExtension(
                    extension_id=ext_id,
                    source_dir=source_dir,
                    error=f"{type(e).__name__}: {e}",
                    manifest=manifest,
                    security_findings=security_findings,
                )
            )
    return report
