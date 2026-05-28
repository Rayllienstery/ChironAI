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
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path)

    safe = policy.match(extension_id="sample-ext", ref="v1.2.2")
    by_ref = policy.match(extension_id="sample-ext", ref="v1.2.3")
    by_repo = policy.match(extension_id="other-ext", repository_id="R_blocked")

    assert safe.matched is False
    assert by_ref.to_dict() == {
        "matched": True,
        "reason": "bad release",
        "source": "test",
        "matched_on": "extension_id",
    }
    assert by_repo.matched is True
    assert by_repo.matched_on == "repository_id"


def test_extension_blocklist_missing_file_is_empty(tmp_path: Path) -> None:
    policy = ExtensionBlocklistPolicy("missing.json", project_root=tmp_path)

    assert policy.load() == []
    assert policy.match(extension_id="sample-ext").matched is False
