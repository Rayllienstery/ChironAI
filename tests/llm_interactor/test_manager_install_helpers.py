from __future__ import annotations

from types import SimpleNamespace

import pytest
from llm_interactor.install_state import InstalledExtensionRecord
from llm_interactor.manager_install_helpers import (
    capability_expansion,
    enabled_capability_ids,
    entry_with_version_payload,
    install_provenance,
    resolve_install_target,
    validate_compatibility,
    validate_install_manifest,
)


def test_enabled_capability_ids_respects_dict_enabled_flag() -> None:
    caps = {"chat": True, "docker": {"enabled": False}, "tab_ui": {"enabled": True}}
    assert enabled_capability_ids(caps) == {"chat", "tab_ui"}


def test_validate_compatibility_rejects_unknown_app() -> None:
    with pytest.raises(ValueError, match="unsupported extension app compatibility"):
        validate_compatibility({"app": "other"})


def test_validate_install_manifest_rejects_id_mismatch() -> None:
    entry = {"id": "sample-ext"}
    manifest = SimpleNamespace(
        id="other-ext",
        version="1.0.0",
        compatibility={},
    )
    with pytest.raises(ValueError, match="manifest id mismatch"):
        validate_install_manifest(entry, manifest, "1.0.0")


def test_entry_with_version_payload_merges_release_fields() -> None:
    merged = entry_with_version_payload(
        {"id": "sample-ext"},
        {"archive_url": "https://github.com/acme/widget/archive/v1.zip", "digest": "sha256:abc"},
    )
    assert merged["archive_url"] == "https://github.com/acme/widget/archive/v1.zip"
    assert merged["digest"] == "sha256:abc"


def test_install_provenance_marks_github_release_asset() -> None:
    provenance = install_provenance(
        {"repository": "https://github.com/acme/widget", "archive_url": "https://github.com/acme/widget/archive/v1.zip"},
        "v1.0.0",
        storage_version="v1.0.0",
    )
    assert provenance["provenance_level"] == "github_release_asset"
    assert provenance["selected_ref"] == "v1.0.0"
    assert provenance["storage_version"] == "v1.0.0"


def test_capability_expansion_flags_high_risk_caps() -> None:
    existing = InstalledExtensionRecord(
        id="sample-ext",
        version="1.0.0",
        enabled=True,
        installed=True,
        capabilities={"chat": True},
    )

    def _installed_capabilities(record: InstalledExtensionRecord) -> dict[str, object]:
        assert record.id == "sample-ext"
        return {"chat": True}

    expansion = capability_expansion(
        existing,
        {"chat": True, "docker": True},
        installed_capabilities_fn=_installed_capabilities,
    )
    assert len(expansion) == 1
    assert expansion[0]["id"] == "docker"
    assert expansion[0]["requires_user_consent"] is True


class _RepoClient:
    def releases(self, repository: str) -> list[dict[str, object]]:
        _ = repository
        return [{"ref": "v2.0.0", "archive_url": "https://github.com/acme/widget/archive/v2.0.0.zip"}]

    def latest_release(self, repository: str) -> dict[str, object]:
        _ = repository
        return {"ref": "v2.0.0", "archive_url": "https://github.com/acme/widget/archive/v2.0.0.zip"}


def test_resolve_install_target_prefers_matching_release() -> None:
    entry = {"id": "sample-ext", "repository": "https://github.com/acme/widget"}
    resolved, ref = resolve_install_target(
        entry,
        "v2.0.0",
        repository_client=_RepoClient(),
    )
    assert ref == "v2.0.0"
    assert resolved["archive_url"] == "https://github.com/acme/widget/archive/v2.0.0.zip"
