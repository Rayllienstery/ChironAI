from __future__ import annotations

import json

import pytest

from application.codex_launcher import (
    CodexLauncherError,
    _proxy_api_key_module,
    build_codex_argv,
    build_codex_env,
    codex_config_path,
    codex_home,
    ide_builds,
    proxy_key_status,
    reveal_existing_proxy_key,
    selected_ide_build,
    write_codex_profile,
)
from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY, dump_builds_json


class _Repo:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_app_setting(self, key: str):
        return self.data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.data[key] = value


def test_ide_builds_filters_enabled_builds() -> None:
    builds = [
        {"id": "web", "ide_mode": False},
        {"id": "codex", "ide_mode": True},
        {"id": "legacy"},
    ]

    assert [item["id"] for item in ide_builds(builds)] == ["codex"]


def test_selected_ide_build_validates_requested_model() -> None:
    builds = [{"id": "web", "ide_mode": False}, {"id": "codex", "ide_mode": True}]

    assert selected_ide_build(builds, "codex")["id"] == "codex"
    with pytest.raises(CodexLauncherError, match="not enabled"):
        selected_ide_build(builds, "web")
    with pytest.raises(CodexLauncherError, match="not found"):
        selected_ide_build(builds, "missing")


def test_reveal_existing_proxy_key_requires_recoverable_key() -> None:
    repo = _Repo()
    api_key_module = _proxy_api_key_module()

    with pytest.raises(CodexLauncherError, match="not configured"):
        reveal_existing_proxy_key(repo)

    plaintext, record = api_key_module.generate_proxy_api_key_record(repo)
    api_key_module.store_proxy_api_key_record(repo, record)

    assert proxy_key_status(repo)["recoverable"] is True
    assert reveal_existing_proxy_key(repo) == plaintext


def test_write_codex_profile_is_idempotent(tmp_path) -> None:
    target = tmp_path / "config.toml"
    target.write_text('[profiles.other]\nmodel_provider = "other"\n', encoding="utf-8")

    write_codex_profile("http://127.0.0.1:8080/v1", config_path=target)
    write_codex_profile("http://127.0.0.1:9090/v1/", config_path=target)

    text = target.read_text(encoding="utf-8")
    assert text.count("[profiles.chironai-proxy]") == 1
    assert text.count("[model_providers.chironai-proxy]") == 1
    assert "openai_base_url" not in text
    assert 'base_url = "http://127.0.0.1:9090/v1/"' in text
    assert 'wire_api = "responses"' in text
    assert 'env_key = "OPENAI_API_KEY"' in text
    assert "[profiles.other]" in text


def test_default_codex_config_path_is_chironai_scoped() -> None:
    assert codex_config_path() == codex_home() / "config.toml"
    assert codex_config_path().parts[-3:] == (".chironai", "codex", "config.toml")


def test_build_codex_argv_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEP_ME", "1")

    assert build_codex_argv("Agent-high", ["--sandbox", "workspace-write"]) == [
        "codex",
        "--profile",
        "chironai-proxy",
        "-m",
        "Agent-high",
        "--sandbox",
        "workspace-write",
    ]
    env = build_codex_env("secret-key")
    assert env["OPENAI_API_KEY"] == "secret-key"
    assert env["CODEX_HOME"] == str(codex_home())
    assert env["KEEP_ME"] == "1"


def test_builds_storage_roundtrips_ide_mode() -> None:
    repo = _Repo()
    builds = [{"id": "Agent-high", "ide_mode": True}]
    repo.set_app_setting(LLM_PROXY_BUILDS_APP_KEY, dump_builds_json(builds))

    assert json.loads(repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY))[0]["ide_mode"] is True
