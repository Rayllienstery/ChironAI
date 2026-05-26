from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from application.codex_launcher import _proxy_api_key_module
from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY, dump_builds_json


def _load_codex_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "codex-launcher" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_codex_launcher_extension_provider", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Repo:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_app_setting(self, key: str):
        return self.data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.data[key] = value


def _extension(repo: _Repo):
    mod = _load_codex_provider_module()
    host = SimpleNamespace(get_settings_repository=lambda: repo)
    manifest = SimpleNamespace(
        id="codex-launcher",
        title="Codex",
        description="",
        icon="icons/codex-light.svg",
        metadata={"tab_ui": {"id": "codex", "title": "Codex", "icon": "icons/codex-light.svg", "order": 55}},
    )
    return mod.CodexLauncherExtension(host, manifest), mod


def test_codex_launcher_tab_payload_reports_ide_builds(monkeypatch) -> None:
    repo = _Repo()
    repo.set_app_setting(
        LLM_PROXY_BUILDS_APP_KEY,
        dump_builds_json(
            [
                {
                    "id": "Agent-high",
                    "display_name": "Agent High",
                    "provider_id": "ollama",
                    "model": "qwen3:latest",
                    "prompt_name": "system_senior_ios_assistant_v1",
                    "ide_mode": True,
                    "num_ctx": 65536,
                }
            ]
        ),
    )
    api_key_module = _proxy_api_key_module()
    _plaintext, record = api_key_module.generate_proxy_api_key_record(repo)
    api_key_module.store_proxy_api_key_record(repo, record)
    ext, mod = _extension(repo)
    monkeypatch.setattr(mod, "codex_status", lambda: {"installed": True, "path": "codex", "version": "codex 1.2.3"})
    monkeypatch.setattr(mod, "check_proxy_reachable", lambda *args, **kwargs: {"data": []})

    descriptor = ext.get_tab_descriptor()
    payload = ext.get_tab_payload()

    assert descriptor["id"] == "codex"
    assert descriptor["icon"] == "icons/codex-light.svg"
    assert descriptor["status"]["ide_builds_count"] == 1
    sections = payload["schema"]["pages"][0]["sections"]
    components = next(section["components"] for section in sections if section.get("id") == "builds")
    assert any(item.get("type") == "select" and item.get("key") == "selected_build" for item in components)
    table = next(item for item in components if item.get("type") == "table")
    assert table["rows"][0]["id"] == "Agent-high"
    assert payload["state"]["command"] == "chironai codex --model Agent-high"


def test_codex_launcher_configure_action_writes_profile(tmp_path) -> None:
    repo = _Repo()
    repo.set_app_setting(
        LLM_PROXY_BUILDS_APP_KEY,
        dump_builds_json(
            [
                {
                    "id": "Agent-high",
                    "provider_id": "ollama",
                    "model": "qwen3:latest",
                    "prompt_name": "system_senior_ios_assistant_v1",
                    "ide_mode": True,
                    "num_ctx": 65536,
                }
            ]
        ),
    )
    api_key_module = _proxy_api_key_module()
    _plaintext, record = api_key_module.generate_proxy_api_key_record(repo)
    api_key_module.store_proxy_api_key_record(repo, record)
    ext, _mod = _extension(repo)
    target = tmp_path / "config.toml"

    result = ext.run_action("configure_codex", {"selected_build": "Agent-high", "config_path": str(target)})

    assert result["ok"] is True
    assert result["command"] == "chironai codex --model Agent-high"
    text = target.read_text(encoding="utf-8")
    assert text.count("[profiles.chironai-proxy]") == 1
    assert 'model = "Agent-high"' in text
    assert "model_catalog_json" in text
    catalog = json.loads((tmp_path / "models.json").read_text(encoding="utf-8"))
    assert catalog["models"][0]["slug"] == "Agent-high"
    assert catalog["models"][0]["context_window"] == 65536
