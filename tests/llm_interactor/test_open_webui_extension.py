from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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
        self.pulled = False
        self.started = False
        self.stopped = False

    def container_running(self, name: str):
        return self.running, ""

    def container_exists(self, name: str) -> bool:
        return self.exists

    def container_env(self, name: str, key: str) -> str:
        return self.env

    def start_container(self, name: str):
        self.started = True
        self.running = True
        return True, "started"

    def stop_container(self, name: str):
        self.stopped = True
        self.running = False
        return True, "stopped"

    def remove_container(self, name: str):
        self.exists = False
        self.running = False
        return True, "removed"

    def pull_image(self, image: str):
        self.pulled = True
        return True, "pulled"

    def run_container(self, cfg):
        self.exists = True
        self.running = True
        return True, "created"


def _extension(repo: _Repo, docker: _Docker):
    mod = _load_open_webui_provider_module()
    host = SimpleNamespace(get_settings_repository=lambda: repo)
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
    return mod.OpenWebUiExtension(host, manifest, docker=docker), mod


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
    assert payload["frame"]["id"] == "open-webui-iframe-frame"
    assert payload["content"]["type"] == "iframe"
    assert payload["content"]["src"] == "http://localhost:3000"
    assert any(action["id"] == "stop" for action in payload["content"]["actions"])


def test_open_webui_extension_actions_and_legacy_setting_migration() -> None:
    repo = _Repo()
    docker = _Docker()
    ext, mod = _extension(repo, docker)
    repo.set_app_setting(mod.LEGACY_BACKEND_KEY, "host.docker.internal:8080")

    payload = ext.get_tab_payload()
    assert repo.get_app_setting(mod.LEGACY_BACKEND_KEY) == ""
    assert repo.get_app_setting(mod.BACKEND_KEY) == "http://host.docker.internal:8080"
    assert payload["content"]["fields"][0]["value"] == "http://host.docker.internal:8080"

    saved = ext.run_action("save_backend", {"backend_url": "localhost:9999"})
    assert saved["ok"] is True
    assert repo.get_app_setting(mod.BACKEND_KEY) == "http://localhost:9999"

    started = ext.run_action("start", {})
    assert started["ok"] is True
    assert docker.pulled is True
    assert docker.running is True

    stopped = ext.run_action("stop", {})
    assert stopped["ok"] is True
    assert docker.stopped is True
