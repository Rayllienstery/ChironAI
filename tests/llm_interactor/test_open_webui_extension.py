from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_open_webui_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "open-webui" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_open_webui_extension_provider", path)
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


class _Docker:
    def __init__(self) -> None:
        self.running = False
        self.exists = False
        self.env = ""
        self.ensure_spec: Any | None = None
        self.stopped = ""

    def inspect_container(self, name: str):
        return SimpleNamespace(
            exists=self.exists or self.running,
            running=self.running,
            name=name,
            env={"OLLAMA_BASE_URL": self.env} if self.env else {},
        )

    def ensure_container(self, spec: Any) -> dict[str, Any]:
        self.ensure_spec = spec
        self.exists = True
        self.running = True
        return {"ok": True, "container": spec.name, "image": spec.image, "message": "created"}

    def stop_container(self, name: str) -> dict[str, Any]:
        self.stopped = name
        self.running = False
        return {"ok": True, "container": name, "message": "stopped"}


def _extension(repo: _Repo, docker: _Docker):
    mod = _load_open_webui_provider_module()
    host = SimpleNamespace(get_settings_repository=lambda: repo, docker_runtime=docker)
    manifest = SimpleNamespace(
        id="open-webui",
        title="Open WebUI",
        description="",
        icon="icons/open-webui-light.svg",
        metadata={
            "tab_ui": {
                "title": "Open WebUI",
                "icon": "icons/open-webui-light.svg",
                "frame": {
                    "id": "open-webui-iframe-frame",
                    "type": "iframe",
                    "chrome": "open-webui-service",
                    "asset_scope": "extension",
                },
            }
        },
    )
    return mod.OpenWebUiExtension(host, manifest), mod


def test_open_webui_extension_descriptor_and_iframe_payload() -> None:
    repo = _Repo()
    docker = _Docker()
    docker.running = True
    ext, _mod = _extension(repo, docker)

    descriptor = ext.get_tab_descriptor()
    payload = ext.get_tab_payload()

    assert descriptor["id"] == "open-webui"
    assert descriptor["title"] == "Open WebUI"
    assert descriptor["icon"] == "icons/open-webui-light.svg"
    assert descriptor["frame"]["type"] == "iframe"
    assert descriptor["status"]["running"] is True
    assert payload["frame"]["type"] == "iframe"
    assert payload["content"]["type"] == "service_panel"
    assert payload["content"]["title"] == "Open WebUI"
    assert any(field.get("key") == "backend_url" for field in payload["content"]["fields"])
    assert any(action.get("id") == "stop" for action in payload["content"]["actions"])
    assert any(item.get("label") == "Container" and item.get("value") == "open-webui" for item in payload["content"]["details"])
    assert "schema" in payload
    components = payload["schema"]["pages"][0]["sections"][0]["components"]
    assert any(c.get("type") == "action" and c.get("action_id") == "stop" for c in components)


def test_open_webui_extension_actions_and_legacy_setting_migration() -> None:
    repo = _Repo()
    docker = _Docker()
    ext, mod = _extension(repo, docker)
    repo.set_app_setting(mod.LEGACY_BACKEND_KEY, "host.docker.internal:8080")

    payload = ext.get_tab_payload()
    assert repo.get_app_setting(mod.LEGACY_BACKEND_KEY) == ""
    assert repo.get_app_setting(mod.BACKEND_KEY) == "http://host.docker.internal:8080"
    components = payload["schema"]["pages"][0]["sections"][0]["components"]
    backend_field = next(c for c in components if c.get("type") == "input" and c.get("key") == "backend_url")
    assert backend_field["value"] == "http://host.docker.internal:8080"

    saved = ext.run_action("save_backend", {"backend_url": "localhost:9999"})
    assert saved["ok"] is True
    assert repo.get_app_setting(mod.BACKEND_KEY) == "http://localhost:9999"

    started = ext.run_action("start", {})
    assert started["ok"] is True
    assert docker.running is True
    assert docker.ensure_spec.name == "open-webui"
    assert docker.ensure_spec.image == "open-webui/open-webui:main"
    assert docker.ensure_spec.ports == ["3000:8080"]
    assert docker.ensure_spec.env == {"OLLAMA_BASE_URL": "http://localhost:9999"}
    assert docker.ensure_spec.restart == "unless-stopped"
    assert docker.ensure_spec.labels["chironai.extension"] == "open-webui"

    stopped = ext.run_action("stop", {})
    assert stopped["ok"] is True
    assert docker.stopped == "open-webui"


def test_open_webui_extension_reports_missing_docker_runtime() -> None:
    mod = _load_open_webui_provider_module()
    repo = _Repo()
    host = SimpleNamespace(get_settings_repository=lambda: repo)
    manifest = SimpleNamespace(id="open-webui", title="Open WebUI", description="", icon="", metadata={})
    ext = mod.OpenWebUiExtension(host, manifest)

    started = ext.run_action("start", {})
    stopped = ext.run_action("stop", {})

    assert started["ok"] is False
    assert started["message"] == "Docker runtime is unavailable"
    assert stopped["ok"] is False
    assert stopped["message"] == "Docker runtime is unavailable"
