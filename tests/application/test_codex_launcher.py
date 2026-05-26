from __future__ import annotations

import json

import pytest

import application.codex_launcher as codex_launcher
from application.codex_launcher import (
    CodexLauncherError,
    _proxy_api_key_module,
    build_codex_argv,
    build_codex_env,
    codex_model_catalog_entry,
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
    target.write_text(
        '[profiles.other]\nmodel_provider = "other"\n\n'
        '[profiles.chironai-proxy.windows]\nsandbox = "elevated"\n',
        encoding="utf-8",
    )
    build = {
        "id": "Hard-worker",
        "display_name": "Hard worker",
        "ide_mode": True,
        "num_ctx": 202752,
        "num_predict": 32768,
    }
    builds = [
        build,
        {"id": "gemini", "display_name": "Gemini", "ide_mode": True, "num_ctx": 131072},
    ]

    write_codex_profile("http://127.0.0.1:8080/v1", config_path=target, build=build, builds=builds)
    write_codex_profile("http://127.0.0.1:9090/v1/", config_path=target, build=build, builds=builds)

    text = target.read_text(encoding="utf-8")
    assert text.count("[profiles.chironai-proxy]") == 1
    assert text.count("[model_providers.chironai-proxy]") == 1
    assert "openai_base_url" not in text
    assert "model_context_window" not in text
    assert "[profiles.chironai-proxy.windows]" not in text
    assert 'sandbox = "elevated"' not in text
    assert f'sandbox_mode = "{codex_launcher.CODEX_SANDBOX_MODE}"' in text
    assert 'model = "Hard-worker"' in text
    assert "model_catalog_json" in text
    assert 'base_url = "http://127.0.0.1:9090/v1/"' in text
    assert 'wire_api = "responses"' in text
    assert 'env_key = "OPENAI_API_KEY"' in text
    assert "[profiles.other]" in text

    catalog = json.loads((tmp_path / "models.json").read_text(encoding="utf-8"))
    rows = {item["slug"]: item for item in catalog["models"]}
    assert set(rows) == {"Hard-worker", "gemini"}
    assert rows["Hard-worker"]["display_name"] == "Hard worker"
    assert rows["Hard-worker"]["context_window"] == 202752
    assert rows["Hard-worker"]["max_context_window"] == 202752
    assert rows["Hard-worker"]["max_output_tokens"] == 32768
    assert rows["Hard-worker"]["prefer_websockets"] is False
    assert rows["Hard-worker"]["default_reasoning_level"] is None
    assert rows["Hard-worker"]["apply_patch_tool_type"] == "freeform"
    assert rows["Hard-worker"]["web_search_tool_type"] == "text"
    assert rows["Hard-worker"]["shell_type"] == "shell_command"
    assert rows["Hard-worker"]["input_modalities"] == ["text", "image"]
    assert rows["Hard-worker"]["supports_image_detail_original"] is True
    assert rows["Hard-worker"]["truncation_policy"] == {"mode": "tokens", "limit": 10000}
    assert rows["Hard-worker"]["supports_parallel_tool_calls"] is True
    assert rows["Hard-worker"]["supported_reasoning_levels"] == []
    assert rows["Hard-worker"]["reasoning_summary_format"] == "none"
    assert rows["Hard-worker"]["default_reasoning_summary"] == "none"
    assert rows["Hard-worker"]["visibility"] == "list"
    assert rows["Hard-worker"]["supported_in_api"] is True
    assert rows["Hard-worker"]["priority"] == 100
    assert "ChironAI LLM Proxy" in rows["Hard-worker"]["base_instructions"]
    assert rows["Hard-worker"]["model_messages"]["instructions_template"].endswith("{{ personality }}")
    assert "personality_pragmatic" in rows["Hard-worker"]["model_messages"]["instructions_variables"]
    assert rows["Hard-worker"]["supports_reasoning_summaries"] is False
    assert rows["Hard-worker"]["effective_context_window_percent"] == 95
    assert rows["Hard-worker"]["experimental_supported_tools"] == []


def test_codex_model_catalog_entry_uses_build_token_limits() -> None:
    row = codex_model_catalog_entry(
        {
            "id": "Hard-worker",
            "display_name": "Hard worker",
            "model": "deepseek-v4-pro:cloud",
            "num_ctx": 131072,
            "num_predict": 16384,
        }
    )

    assert row["slug"] == "Hard-worker"
    assert row["display_name"] == "Hard worker"
    assert row["context_window"] == 131072
    assert row["max_context_window"] == 131072
    assert row["max_output_tokens"] == 16384


def test_codex_model_catalog_entry_defaults_context_window() -> None:
    row = codex_model_catalog_entry({"id": "Giant", "num_predict": 200000})

    assert row["context_window"] == 131072
    assert row["max_context_window"] == 131072
    assert row["max_output_tokens"] == 131071


def test_default_codex_config_path_is_chironai_scoped() -> None:
    assert codex_config_path() == codex_home() / "config.toml"
    assert codex_config_path().parts[-3:] == (".chironai", "codex", "config.toml")


def test_build_codex_argv_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEP_ME", "1")
    monkeypatch.setattr(codex_launcher, "_find_openai_codex_path", lambda: "codex")

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
