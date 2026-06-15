from __future__ import annotations

from types import SimpleNamespace

from llm_interactor.discovery import FailedExtension
from llm_interactor.install_state import InstalledExtensionRecord
from llm_interactor.manager_blocklist import (
    blocklist_match_for_entry,
    blocklist_match_for_record,
    blocklist_match_for_values,
    disable_blocklisted_records,
    disable_security_blocked_extensions,
    publisher_name,
)


class _BlocklistPolicy:
    def __init__(self, *, matched: bool = False, reason: str = "blocked") -> None:
        self._matched = matched
        self._reason = reason
        self.calls: list[dict[str, str]] = []

    def match(self, **kwargs: str) -> SimpleNamespace:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            matched=self._matched,
            reason=self._reason,
            source="test",
            matched_on="extension_id",
            to_dict=lambda: {
                "matched": self._matched,
                "reason": self._reason,
                "source": "test",
                "matched_on": "extension_id",
            },
        )


class _MemoryRepo:
    def __init__(self, records: list[InstalledExtensionRecord]) -> None:
        self._records = list(records)
        self.saved: list[list[InstalledExtensionRecord]] = []

    def list_records(self) -> list[InstalledExtensionRecord]:
        return list(self._records)

    def save_records(self, records: list[InstalledExtensionRecord]) -> None:
        self._records = list(records)
        self.saved.append(list(records))


def test_publisher_name_reads_dict_name_or_id() -> None:
    assert publisher_name({"name": "Acme"}) == "Acme"
    assert publisher_name({"id": "acme-id"}) == "acme-id"
    assert publisher_name("plain") == "plain"


def test_blocklist_match_for_values_returns_no_match_when_policy_missing() -> None:
    match = blocklist_match_for_values(None, extension_id="sample-ext")
    assert match["matched"] is False


def test_blocklist_match_for_values_fail_closed_on_policy_error() -> None:
    class _BrokenPolicy:
        def match(self, **kwargs: str) -> SimpleNamespace:
            raise RuntimeError("boom")

    match = blocklist_match_for_values(_BrokenPolicy(), extension_id="sample-ext")
    assert match["matched"] is True
    assert "Blocklist evaluation error" in match["reason"]


def test_blocklist_match_for_entry_uses_publisher_name() -> None:
    policy = _BlocklistPolicy()
    blocklist_match_for_entry(
        policy,
        {
            "id": "sample-ext",
            "repository": "https://github.com/acme/widget",
            "publisher": {"name": "Acme Labs"},
        },
    )
    assert policy.calls[0]["publisher"] == "Acme Labs"


def test_blocklist_match_for_record_uses_provenance_ref() -> None:
    policy = _BlocklistPolicy()
    record = InstalledExtensionRecord(
        id="sample-ext",
        version="1.0.0",
        enabled=True,
        installed=True,
        provenance={"selected_ref": "v1.0.0", "repository": "https://github.com/acme/widget"},
    )
    blocklist_match_for_record(policy, record)
    assert policy.calls[0]["ref"] == "v1.0.0"


def test_disable_security_blocked_extensions_disables_matching_records() -> None:
    record = InstalledExtensionRecord(
        id="unsafe-ext",
        version="1.0.0",
        enabled=True,
        installed=True,
    )
    repo = _MemoryRepo([record])
    failed = [
        FailedExtension(
            extension_id="unsafe-ext",
            source_dir=None,
            error="security audit failed",
            security_findings=[{"severity": "critical", "code": "UNSAFE"}],
        )
    ]
    disable_security_blocked_extensions(failed, repo=repo, utc_now=lambda: "2026-06-16T00:00:00Z")
    updated = repo.list_records()[0]
    assert updated.enabled is False
    assert updated.security_scan["status"] == "blocked"
    assert updated.blocked_reason == "security audit failed"


def test_disable_blocklisted_records_disables_installed_matches() -> None:
    record = InstalledExtensionRecord(
        id="blocked-ext",
        version="1.0.0",
        enabled=True,
        installed=True,
    )
    repo = _MemoryRepo([record])
    disable_blocklisted_records(
        repo=repo,
        blocklist_policy=_BlocklistPolicy(matched=True, reason="emergency block"),
        utc_now=lambda: "2026-06-16T00:00:00Z",
    )
    updated = repo.list_records()[0]
    assert updated.enabled is False
    assert updated.security_scan["scanner"] == "chironai_blocklist"
    assert updated.blocked_reason == "emergency block"
