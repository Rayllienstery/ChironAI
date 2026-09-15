from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from application.phone_host_scripts import (
    PHONE_HOST_SCRIPTS_SETTING,
    list_phone_host_scripts,
    load_phone_host_enabled_map,
    phone_host_repo_root,
    save_phone_host_enabled_map,
    set_phone_host_script_enabled,
)


def test_parse_enabled_map_accepts_json_and_ignores_junk() -> None:
    from application import phone_host_scripts as scripts

    assert scripts._parse_enabled_map("not-json") == {}
    assert scripts._parse_enabled_map(["x"]) == {}
    assert scripts._parse_enabled_map({"": True, "phone-host": 0}) == {"phone-host": False}


def test_repo_root_honors_env_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHIRONAI_REPO_ROOT", str(tmp_path))
    assert phone_host_repo_root() == tmp_path.resolve()


def test_load_save_and_list_scripts(monkeypatch, tmp_path) -> None:
    scripts_dir = tmp_path / "scripts" / "phone_host"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "phone-host.ps1").write_text("# stub", encoding="utf-8")
    (scripts_dir / "phone-host.cmd").write_text("stub", encoding="utf-8")
    monkeypatch.setattr("application.phone_host_scripts.phone_host_scripts_dir", lambda: scripts_dir)
    monkeypatch.setattr(
        "application.phone_host_scripts.phone_host_enabled_path",
        lambda: scripts_dir / "enabled.json",
    )
    saved: dict[str, str] = {}
    repo = SimpleNamespace(
        get_app_setting=lambda _key: json.dumps({"phone-host": False}),
        set_app_setting=lambda key, value: saved.update({key: value}),
    )

    loaded = load_phone_host_enabled_map(repo)
    assert loaded["phone-host"] is False
    payload = save_phone_host_enabled_map({"phone-host": True, "setup-openssh": False}, repo)
    assert payload["setup-openssh"] is False
    assert PHONE_HOST_SCRIPTS_SETTING in saved
    rows = list_phone_host_scripts(repo)
    by_id = {row["id"]: row for row in rows}
    assert by_id["phone-host"]["exists"] is True
    assert by_id["phone-host"]["wrapper_exists"] is True
    updated = set_phone_host_script_enabled("setup-openssh", False, repo)
    assert {row["id"]: row["enabled"] for row in updated}["setup-openssh"] is False
    with pytest.raises(KeyError):
        set_phone_host_script_enabled("missing", True, repo)
