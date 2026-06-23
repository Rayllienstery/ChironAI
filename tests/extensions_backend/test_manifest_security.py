from __future__ import annotations

import json
from pathlib import Path

import pytest
from llm_interactor.discovery import discover_extensions, load_manifest_from_dir
from llm_interactor.manifest import manifest_sha256

from llm_interactor import EXTENSION_API_VERSION, ProviderHostContext


def _write_manifest(
    root: Path,
    *,
    ext_id: str = "sample-ext",
    api_version: str = EXTENSION_API_VERSION,
    ext_type: str = "llm_provider",
    capabilities: dict[str, object] | None = None,
    manifest_digest: str | None = None,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    raw: dict[str, object] = {
        "id": ext_id,
        "version": "1.0.0",
        "api_version": api_version,
        "type": ext_type,
        "title": "Sample",
        "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
        "capabilities": dict(capabilities or {"chat": True}),
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    if manifest_digest is not None:
        raw["manifest_sha256"] = manifest_digest
    (root / "chironai-extension.json").write_text(json.dumps(raw), encoding="utf-8")
    return raw


def _write_provider(root: Path, capabilities: str) -> None:
    backend = root / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    (backend / "provider.py").write_text(
        "\n".join(
            [
                "from core.contracts.llm_runtime import ProviderCapabilities, ProviderDescriptor",
                "",
                "class Provider:",
                "    def describe(self):",
                "        return ProviderDescriptor(",
                "            id='sample',",
                "            extension_id='sample-ext',",
                "            title='Sample',",
                f"            capabilities=ProviderCapabilities({capabilities}),",
                "        )",
                "",
                "def create_provider(host_context, manifest):",
                "    return Provider()",
            ]
        ),
        encoding="utf-8",
    )


def test_manifest_sha256_accepts_canonical_embedded_digest(tmp_path: Path) -> None:
    ext = tmp_path / "sample-ext"
    raw = _write_manifest(ext, manifest_digest="")
    digest = manifest_sha256(raw)
    raw["manifest_sha256"] = digest
    (ext / "chironai-extension.json").write_text(json.dumps(raw), encoding="utf-8")

    manifest = load_manifest_from_dir(ext)

    assert manifest.manifest_sha256 == digest


def test_manifest_sha256_rejects_mismatch(tmp_path: Path) -> None:
    ext = tmp_path / "sample-ext"
    _write_manifest(ext, manifest_digest="0" * 64)

    with pytest.raises(ValueError, match="manifest_sha256 mismatch"):
        load_manifest_from_dir(ext)


def test_old_manifest_api_version_is_rejected(tmp_path: Path) -> None:
    ext = tmp_path / "sample-ext"
    _write_manifest(ext, api_version="0")

    with pytest.raises(ValueError, match="unsupported manifest api_version"):
        load_manifest_from_dir(ext)


def test_llm_provider_cannot_advertise_undeclared_capabilities(tmp_path: Path) -> None:
    ext = tmp_path / "sample-ext"
    _write_manifest(ext, capabilities={"chat": True})
    _write_provider(
        ext,
        "chat=True, streaming=False, model_listing=False, health_check=False, tools=True",
    )
    host = ProviderHostContext(project_root=tmp_path, get_settings_repository=lambda: object(), chat_client=None)

    report = discover_extensions([ext], host_context=host, use_sandbox=False)

    assert report.loaded == []
    assert len(report.failed) == 1
    assert "provider capabilities not declared in manifest: tools" in report.failed[0].error
