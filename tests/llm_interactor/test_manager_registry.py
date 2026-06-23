from __future__ import annotations

import pytest
from llm_interactor.manager_registry import (
    enrich_registry_entry,
    fetch_extension_details,
    load_registry_entries,
    registry_diagnostics_payload,
)


class _RegistryClient:
    def __init__(self, entries: list[dict[str, object]]) -> None:
        self._entries = entries
        self.registry_url = "https://example.com/registry.json"

    def load(self) -> list[dict[str, object]]:
        return list(self._entries)

    def load_with_diagnostics(self) -> object:
        return type(
            "Result",
            (),
            {
                "registry_url": self.registry_url,
                "diagnostics": [],
                "entries": self._entries,
            },
        )()


class _RepositoryClient:
    def latest_release(self, repository: str) -> dict[str, object]:
        _ = repository
        return {"ref": "v1.0.0", "version": "1.0.0"}

    def releases(self, repository: str) -> list[dict[str, object]]:
        _ = repository
        return [{"ref": "v1.0.0", "version": "1.0.0"}]

    def tags(self, repository: str) -> list[dict[str, object]]:
        _ = repository
        return [{"ref": "main", "version": "main"}]

    def readme(self, repository: str, *, ref: str | None = None) -> dict[str, object]:
        _ = repository
        return {"markdown": "# Hello", "sanitized_html": "<p>Hello</p>", "ref": ref or "main"}


def test_enrich_registry_entry_adds_icon_url_and_blocklist() -> None:
    entry = {
        "id": "sample-ext",
        "repository": "https://github.com/acme/widget",
        "icon": "icons/logo.svg",
        "default_ref": "main",
    }
    enriched = enrich_registry_entry(
        entry,
        blocklist_match_fn=lambda _: {"matched": True, "reason": "blocked"},
        github_raw_asset_url_fn=lambda repo, icon, ref="HEAD": f"{repo}|{icon}|{ref}",
    )
    assert enriched["icon_url"] == "https://github.com/acme/widget|icons/logo.svg|main"
    assert enriched["visibility"] == "blocked"
    assert enriched["blocklist"]["reason"] == "blocked"


def test_load_registry_entries_enriches_all_rows() -> None:
    client = _RegistryClient([{"id": "sample-ext", "repository": "https://github.com/acme/widget"}])
    rows = load_registry_entries(
        client,
        blocklist_match_fn=lambda _: {"matched": False},
        github_raw_asset_url_fn=lambda repo, icon, ref="HEAD": "icon-url",
    )
    assert len(rows) == 1
    assert rows[0]["icon_url"] == "icon-url"


def test_registry_diagnostics_payload_uses_loader_when_available() -> None:
    client = _RegistryClient([{"id": "sample-ext"}])
    payload = registry_diagnostics_payload(client, registry_entries_fn=lambda: [])
    assert payload["registry_url"] == client.registry_url
    assert payload["entries_count"] == 1


def test_fetch_extension_details_raises_for_missing_entry() -> None:
    with pytest.raises(ValueError, match="not found in registry"):
        fetch_extension_details(
            "missing-ext",
            registry_entries_fn=lambda: [{"id": "other-ext"}],
            repository_client=None,
        )


def test_fetch_extension_details_merges_repository_metadata() -> None:
    details = fetch_extension_details(
        "sample-ext",
        registry_entries_fn=lambda: [
            {"id": "sample-ext", "repository": "https://github.com/acme/widget"}
        ],
        repository_client=_RepositoryClient(),
        ref="main",
    )
    assert details["entry"]["id"] == "sample-ext"
    assert details["latest"]["ref"] == "v1.0.0"
    assert details["versions"]
    assert details["readme"]["markdown"] == "# Hello"
