from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_proxy.api_key import generate_proxy_api_key_record, store_proxy_api_key_record


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
        self.image = ""
        self.volumes: list[str] = []
        self.ensure_spec: Any | None = None
        self.stopped = ""
        self.image_check: dict[str, Any] = {
            "status": "up_to_date",
            "message": "Image is up to date",
            "current_version": "main",
            "update_version": "main",
        }

    def inspect_container(self, name: str):
        return SimpleNamespace(
            exists=self.exists or self.running,
            running=self.running,
            name=name,
            image=self.image,
            volumes=self.volumes,
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

    def check_image_update(self, image: str) -> dict[str, Any]:
        return dict(self.image_check)


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
    assert any(action.get("id") == "apply_config" for action in payload["content"]["actions"])
    assert any(action.get("id") == "stop" for action in payload["content"]["actions"])
    assert any(item.get("label") == "Container" and item.get("value") == "open-webui" for item in payload["content"]["details"])
    assert "schema" in payload
    components = payload["schema"]["pages"][0]["sections"][0]["components"]
    assert any(c.get("type") == "action" and c.get("action_id") == "apply_config" for c in components)
    assert any(c.get("type") == "action" and c.get("action_id") == "stop" for c in components)

    service = payload["content"]["service"]
    assert service["name"] == "Open WebUI"
    assert service["icon"] == "deployed_code"
    assert service["backendUrlLabel"] == "Chat backend URL"
    assert service["fieldKey"] == "backend_url"
    service_actions = {a["id"] for a in service["actions"]}
    assert {"refresh", "check_image_version", "apply_config", "stop", "clear_backend", "open_external"} <= service_actions
    service_meta_labels = [m["label"] for m in service["meta"]]
    assert "Container" in service_meta_labels
    assert "Image" in service_meta_labels
    assert "Status" in service_meta_labels
    assert "Image version" in service_meta_labels
    assert "Host URL" in service_meta_labels
    assert "Port" in service_meta_labels
    assert "Backend source" in service_meta_labels
    assert "Chiron OpenAI URL" in service_meta_labels
    assert "Chiron API key" in service_meta_labels
    image_version_tile = next(m for m in service["meta"] if m["label"] == "Image version")
    assert image_version_tile["value"]["label"] == "not checked"
    status_tile = next(m for m in service["meta"] if m["label"] == "Status")
    assert status_tile["value"]["label"] in {"running", "stopped", "ready"}


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
    assert docker.ensure_spec.image == "ghcr.io/open-webui/open-webui:main"
    assert docker.ensure_spec.ports == ["3000:8080"]
    assert docker.ensure_spec.env["OLLAMA_BASE_URL"] == "http://localhost:9999"
    assert docker.ensure_spec.env["ENABLE_OPENAI_API"] == "True"
    assert docker.ensure_spec.env["OPENAI_API_BASE_URLS"] == "http://host.docker.internal:8080/v1"
    assert docker.ensure_spec.env["OPENAI_API_KEYS"].startswith("chiron_sk_")
    assert docker.ensure_spec.volumes == ["open-webui:/app/backend/data"]
    assert docker.ensure_spec.restart == "unless-stopped"
    assert docker.ensure_spec.labels["chironai.extension"] == "open-webui"

    stopped = ext.run_action("stop", {})
    assert stopped["ok"] is True
    assert docker.stopped == "open-webui"


def test_open_webui_extension_uses_existing_recoverable_chiron_key() -> None:
    repo = _Repo()
    docker = _Docker()
    ext, _mod = _extension(repo, docker)
    plaintext, record = generate_proxy_api_key_record(repo)
    store_proxy_api_key_record(repo, record)

    started = ext.run_action("start", {})

    assert started["ok"] is True
    assert docker.ensure_spec.env["OPENAI_API_KEYS"] == plaintext
    assert docker.ensure_spec.env["OPENAI_API_BASE_URLS"] == "http://host.docker.internal:8080/v1"


def test_open_webui_extension_reuses_existing_container_image_for_apply_config() -> None:
    repo = _Repo()
    docker = _Docker()
    docker.exists = True
    docker.image = "open-webui/open-webui:main"
    ext, _mod = _extension(repo, docker)

    applied = ext.run_action("apply_config", {})

    assert applied["ok"] is True
    assert docker.ensure_spec.image == "open-webui/open-webui:main"
    assert docker.ensure_spec.env["OPENAI_API_BASE_URLS"] == "http://host.docker.internal:8080/v1"
    assert docker.ensure_spec.volumes == ["open-webui:/app/backend/data"]


def test_open_webui_extension_preserves_existing_container_data_volume_for_apply_config() -> None:
    repo = _Repo()
    docker = _Docker()
    docker.exists = True
    docker.image = "open-webui/open-webui:main"
    docker.volumes = ["existing_open_webui:/app/backend/data"]
    ext, _mod = _extension(repo, docker)

    applied = ext.run_action("apply_config", {})

    assert applied["ok"] is True
    assert docker.ensure_spec.volumes == ["existing_open_webui:/app/backend/data"]


def test_open_webui_extension_check_image_version_action_and_caching() -> None:
    repo = _Repo()
    docker = _Docker()
    ext, mod = _extension(repo, docker)

    payload = ext.get_tab_payload()
    image_version_tile = next(
        m for m in payload["content"]["service"]["meta"] if m["label"] == "Image version"
    )
    assert image_version_tile["value"]["label"] == "not checked"

    docker.image_check = {
        "status": "up_to_date",
        "message": "Image is up to date",
        "current_version": "main",
        "update_version": "main",
    }
    result = ext.run_action("check_image_version", {})
    assert result["ok"] is True
    assert result["image_version"]["label"] == "up_to_date"
    assert result["image_version"]["tone"] == "success"

    payload = ext.get_tab_payload()
    image_version_tile = next(
        m for m in payload["content"]["service"]["meta"] if m["label"] == "Image version"
    )
    assert image_version_tile["value"]["label"] == "up_to_date"
    assert image_version_tile["value"]["tone"] == "success"

    docker.image_check = {
        "status": "update_available",
        "message": "Update available",
        "current_version": "main@sha1",
        "update_version": "main@sha2",
    }
    result = ext.run_action("check_image_version", {})
    assert result["image_version"]["label"] == "update_available"
    assert result["image_version"]["tone"] == "warning"


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
