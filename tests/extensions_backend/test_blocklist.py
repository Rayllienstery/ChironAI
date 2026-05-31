from __future__ import annotations

import json
from pathlib import Path

from extensions_backend import ExtensionBlocklistPolicy


def test_extension_blocklist_matches_id_ref_and_repository_id(tmp_path: Path) -> None:
    blocklist = tmp_path / "blocklist.json"
    blocklist.write_text(
        json.dumps(
            {
                "blocked": [
                    {
                        "extension_id": "sample-ext",
                        "ref": "v1.2.3",
                        "reason": "bad release",
                        "source": "test",
                    },
                    {
                        "repository_id": "R_blocked",
                        "reason": "repo compromised",
                    },
                    {
                        "match": {"publisher": "Blocked Publisher"},
                        "reason": "publisher blocked",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path)

    safe = policy.match(extension_id="sample-ext", ref="v1.2.2")
    by_ref = policy.match(extension_id="sample-ext", ref="v1.2.3")
    by_repo = policy.match(extension_id="other-ext", repository_id="R_blocked")
    by_publisher = policy.match(extension_id="pub-ext", publisher="Blocked Publisher")

    assert safe.matched is False
    assert by_ref.to_dict() == {
        "matched": True,
        "reason": "bad release",
        "source": "test",
        "matched_on": "extension_id",
    }
    assert by_repo.matched is True
    assert by_repo.matched_on == "repository_id"
    assert by_publisher.matched is True
    assert by_publisher.matched_on == "publisher"


def test_extension_blocklist_missing_file_is_empty(tmp_path: Path) -> None:
    policy = ExtensionBlocklistPolicy("missing.json", project_root=tmp_path)

    assert policy.load() == []
    assert policy.match(extension_id="sample-ext").matched is False


def test_extension_blocklist_uses_local_fallback_when_primary_fails(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback.json"
    fallback.write_text(
        json.dumps({"blocked": [{"extension_id": "sample-ext", "reason": "offline cache"}]}),
        encoding="utf-8",
    )
    policy = ExtensionBlocklistPolicy("missing-primary.json", project_root=tmp_path, fallback_url=str(fallback))

    match = policy.match(extension_id="sample-ext")

    assert match.matched is True
    assert match.reason == "offline cache"


def test_extension_blocklist_ttl_triggers_reload(tmp_path: Path) -> None:
    blocklist = tmp_path / "blocklist.json"
    blocklist.write_text(json.dumps({"blocked": []}), encoding="utf-8")
    policy = ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path, ttl_sec=0.0)

    first_load = policy.load()
    assert first_load == []

    blocklist.write_text(
        json.dumps({"blocked": [{"extension_id": "new-ext", "reason": "added after ttl"}]}),
        encoding="utf-8",
    )
    second_load = policy.load()

    assert len(second_load) == 1
    assert second_load[0]["extension_id"] == "new-ext"


def test_extension_blocklist_stale_rules_kept_on_reload_failure(tmp_path: Path, monkeypatch) -> None:
    blocklist = tmp_path / "blocklist.json"
    blocklist.write_text(
        json.dumps({"blocked": [{"extension_id": "existing-ext", "reason": "was blocked"}]}),
        encoding="utf-8",
    )
    policy = ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path, ttl_sec=60.0)
    policy.load()

    import time
    monkeypatch.setattr(time, "monotonic", lambda: policy._loaded_at + 9999)

    def _raise(*args, **kwargs):
        raise OSError("simulated network/disk failure")

    monkeypatch.setattr(policy, "_read_payload", _raise)

    rules = policy.load()
    assert len(rules) == 1
    assert rules[0]["extension_id"] == "existing-ext"


def test_extension_blocklist_remote_oversized_response_is_rejected(monkeypatch) -> None:
    """An oversized remote blocklist response is rejected and falls back to empty rules.

    The load should NOT raise — it degrades gracefully and logs a warning so the
    host application keeps running rather than crashing.
    """
    from extensions_backend.blocklist import _MAX_BLOCKLIST_RESPONSE_BYTES

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, chunk_size: int):
            _ = chunk_size
            oversized = b"x" * (_MAX_BLOCKLIST_RESPONSE_BYTES + 1)
            yield oversized

    monkeypatch.setattr("requests.get", lambda url, stream, timeout: _Response())
    policy = ExtensionBlocklistPolicy("https://example.invalid/blocklist.json")

    rules = policy.load()

    assert rules == [], "oversized response must yield empty rules for diagnostics"
    match = policy.match(extension_id="any-ext")
    assert match.matched is True
    assert "Blocklist unavailable" in match.reason
