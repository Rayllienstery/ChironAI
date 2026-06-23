"""Blocklist policy matching and security blocking for extensions."""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from llm_interactor.discovery import FailedExtension
from llm_interactor.install_state import InstalledExtensionRecord

_log = logging.getLogger(__name__)

RESTART_SCOPE_PROVIDER_REGISTRY = "provider_registry"


class _RecordsRepo(Protocol):
    def list_records(self) -> list[InstalledExtensionRecord]: ...

    def save_records(self, records: list[InstalledExtensionRecord]) -> None: ...


def publisher_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "").strip()
    return str(value or "").strip()


def blocklist_match_for_values(
    blocklist_policy: Any | None,
    *,
    extension_id: str,
    version: str = "",
    ref: str = "",
    repository: str = "",
    repository_id: str = "",
    publisher: str = "",
    source_path: str = "",
) -> dict[str, Any]:
    if blocklist_policy is None:
        _log.error(
            "Blocklist policy is unavailable (extensions_backend missing?); "
            "extension '%s' will not be checked against emergency blocklist.",
            extension_id,
        )
        return {"matched": False, "reason": "", "source": "", "matched_on": ""}
    try:
        match = blocklist_policy.match(
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


def blocklist_match_for_entry(
    blocklist_policy: Any | None,
    entry: dict[str, Any],
    *,
    version: str = "",
    ref: str = "",
) -> dict[str, Any]:
    return blocklist_match_for_values(
        blocklist_policy,
        extension_id=str(entry.get("id") or ""),
        version=version,
        ref=ref,
        repository=str(entry.get("repository") or entry.get("repo_url") or ""),
        repository_id=str(entry.get("repository_id") or ""),
        publisher=publisher_name(entry.get("publisher")),
        source_path=str(entry.get("source_path") or ""),
    )


def blocklist_match_for_record(
    blocklist_policy: Any | None,
    record: InstalledExtensionRecord,
) -> dict[str, Any]:
    provenance = dict(record.provenance or {})
    source = dict(record.source or {})
    selected_ref = str(provenance.get("selected_ref") or provenance.get("selected_version") or record.version)
    return blocklist_match_for_values(
        blocklist_policy,
        extension_id=record.id,
        version=record.version,
        ref=selected_ref,
        repository=str(
            provenance.get("repository")
            or source.get("repository")
            or source.get("repo_url")
            or source.get("source_path")
            or ""
        ),
        repository_id=str(provenance.get("repository_id") or ""),
        publisher="",
        source_path=str(source.get("source_path") or provenance.get("source_path") or ""),
    )


def disable_security_blocked_extensions(
    failed: list[FailedExtension],
    *,
    repo: _RecordsRepo,
    utc_now: Callable[[], str],
) -> None:
    blocked = [item for item in failed if item.security_findings]
    if not blocked:
        return
    records = repo.list_records()
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
            "scanned_at": utc_now(),
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
        repo.save_records(next_records)


def disable_blocklisted_records(
    *,
    repo: _RecordsRepo,
    blocklist_policy: Any | None,
    utc_now: Callable[[], str],
) -> None:
    records = repo.list_records()
    changed = False
    next_records: list[InstalledExtensionRecord] = []
    for record in records:
        if not record.installed:
            next_records.append(record)
            continue
        match = blocklist_match_for_record(blocklist_policy, record)
        if not match.get("matched"):
            next_records.append(record)
            continue
        scan = {
            "status": "blocked",
            "scanner": "chironai_blocklist",
            "scanned_at": utc_now(),
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
        repo.save_records(next_records)
