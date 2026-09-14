from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_interactor import ProviderHostContext


def _load_ollama_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "ollama-provider" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_ollama_provider_backend", path)
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


class _ChatClient:
    _url = "http://localhost:11434/api/chat"
    _model = "llama3.2"


class _Docker:
    def __init__(self) -> None:
        self.running = False
        self.exists = False
        self.image = ""
        self.ensure_spec: Any | None = None
        self.stopped = ""
        self.image_check_calls: list[str] = []
        self.image_check: dict[str, Any] = {
            "status": "up_to_date",
            "message": "Image is up to date",
            "current_version": "latest",
            "update_version": "latest",
        }

    def inspect_container(self, name: str):
        return SimpleNamespace(
            exists=self.exists or self.running,
            running=self.running,
            name=name,
            image=self.image,
        )

    def ensure_container(self, spec: Any) -> dict[str, Any]:
        self.ensure_spec = spec
        self.exists = True
        self.running = True
        return {"ok": True, "container": spec.name, "image": spec.image, "message": "created"}

    def wait_http(self, url: str, *, path: str, timeout: float, interval: float) -> dict[str, Any]:
        return {"ok": True, "url": f"{url.rstrip('/')}{path}", "status_code": 200}

    def stop_container(self, name: str) -> dict[str, Any]:
        self.stopped = name
        self.running = False
        return {"ok": True, "container": name, "message": "stopped"}

    def check_image_update(self, image: str) -> dict[str, Any]:
        self.image_check_calls.append(image)
        return dict(self.image_check)


def _provider(docker: Any | None, *, repo: Any | None = None, module: Any | None = None):
    module = module or _load_ollama_provider_module()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(
        project_root=root,
        get_settings_repository=lambda: repo or _Repo(),
        chat_client=_ChatClient(),
        docker_runtime=docker,
    )
    manifest = SimpleNamespace(
        id="ollama-provider",
        title="Ollama",
        description="",
        icon="icons/ollama-light.svg",
        tab_ui={},
        metadata={},
    )
    return module.create_provider(host, manifest)


def _docker_card_from_tab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload["schema"]["pages"][0]["sections"]
    for section in sections:
        if section.get("id") == "docker":
            for component in section.get("components") or []:
                if component.get("type") == "docker_card":
                    return component
    raise AssertionError("docker_card component not found in tab payload")


# ---------------------------------------------------------------------------
# docker_card component tests
# ---------------------------------------------------------------------------


def test_ollama_tab_payload_includes_docker_card_component(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    assert card["type"] == "docker_card"
    assert card["name"] == "Ollama"
    assert card["description"] == "Docker-managed Ollama runtime"
    assert card["icon"] == "memory"
    assert card["backendUrl"] == "http://localhost:11434"
    assert card["backendUrlLabel"] == "Chat backend URL"
    assert card["fieldKey"] == "backend_url"
    assert card["autosaveActionId"] == "save_backend"
    # Tab polling must not hit the registry — that hangs sandbox host_calls.
    assert docker.image_check_calls == []


def test_ollama_tab_payload_skips_registry_image_check(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, module=module)

    provider.get_tab_payload()
    assert docker.image_check_calls == []

    result = provider.run_action("check_image_version", {})
    assert result["ok"] is True
    assert docker.image_check_calls


def test_ollama_docker_card_has_expected_meta_tiles(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    meta_labels = [m["label"] for m in card["meta"]]
    assert "Container" in meta_labels
    assert "Image" in meta_labels
    assert "Status" in meta_labels
    assert "Image version" in meta_labels
    assert "Host URL" in meta_labels
    assert "Port" in meta_labels
    assert "Volume mounts" in meta_labels

    container_tile = next(m for m in card["meta"] if m["label"] == "Container")
    assert container_tile["value"] == "chironai-ollama"

    image_tile = next(m for m in card["meta"] if m["label"] == "Image")
    assert image_tile["value"] == "ollama/ollama:latest"

    status_tile = next(m for m in card["meta"] if m["label"] == "Status")
    assert status_tile["value"]["label"] == "Running"
    assert status_tile["value"]["tone"] == "success"

    image_version_tile = next(m for m in card["meta"] if m["label"] == "Image version")
    assert image_version_tile["value"]["label"] == "not checked"
    assert image_version_tile["value"]["tone"] == "neutral"

    port_tile = next(m for m in card["meta"] if m["label"] == "Port")
    assert port_tile["value"] == "11434:11434"


def test_ollama_docker_card_actions_when_running(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    action_ids = {a["id"] for a in card["actions"]}
    assert "refresh" in action_ids
    assert "check_image_version" in action_ids
    assert "stop_service" in action_ids
    assert "open_external" in action_ids
    assert "start_service" not in action_ids

    stop_action = next(a for a in card["actions"] if a["id"] == "stop_service")
    assert stop_action["variant"] == "danger"
    assert stop_action["icon"] == "stop_circle"
    assert "Stop Ollama container" in stop_action.get("confirm", "")


def test_ollama_docker_card_actions_when_stopped(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": False})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = False
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    action_ids = {a["id"] for a in card["actions"]}
    assert "refresh" in action_ids
    assert "check_image_version" in action_ids
    assert "start_service" in action_ids
    assert "open_external" in action_ids
    assert "stop_service" not in action_ids

    start_action = next(a for a in card["actions"] if a["id"] == "start_service")
    assert start_action["variant"] == "primary"
    assert start_action["icon"] == "play_circle"


def test_ollama_docker_card_http_status_when_running(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    assert card["httpStatus"] == "HTTP 11434"


def test_ollama_docker_card_http_status_when_stopped(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": False})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = False
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    assert card["httpStatus"] == ""


# ---------------------------------------------------------------------------
# check_image_version action tests
# ---------------------------------------------------------------------------


def test_ollama_check_image_version_action_returns_tile_and_caches(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    docker.image_check = {
        "status": "up_to_date",
        "message": "Image is up to date",
        "current_version": "latest",
        "update_version": "latest",
    }
    provider = _provider(docker, module=module)

    # Before check: not checked
    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)
    image_version_tile = next(m for m in card["meta"] if m["label"] == "Image version")
    assert image_version_tile["value"]["label"] == "not checked"

    # Run check
    result = provider.run_action("check_image_version", {})
    assert result["ok"] is True
    assert result["image_version"]["label"] == "up_to_date"
    assert result["image_version"]["tone"] == "success"

    # After check: cached
    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)
    image_version_tile = next(m for m in card["meta"] if m["label"] == "Image version")
    assert image_version_tile["value"]["label"] == "up_to_date"
    assert image_version_tile["value"]["tone"] == "success"


def test_ollama_check_image_version_update_available(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = True
    docker.running = True
    docker.image_check = {
        "status": "update_available",
        "message": "Update available",
        "current_version": "latest@sha1",
        "update_version": "latest@sha2",
    }
    provider = _provider(docker, module=module)

    result = provider.run_action("check_image_version", {})
    assert result["ok"] is True
    assert result["image_version"]["label"] == "update_available"
    assert result["image_version"]["tone"] == "warning"


def test_ollama_check_image_version_docker_unavailable(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    provider = _provider(None, module=module)

    result = provider.run_action("check_image_version", {})
    assert result["ok"] is True
    assert result["image_version"]["label"] == "unavailable"
    assert result["image_version"]["tone"] == "error"


# ---------------------------------------------------------------------------
# save_backend action test
# ---------------------------------------------------------------------------


def test_ollama_save_backend_action(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    repo = _Repo()
    docker = _Docker()
    docker.exists = True
    docker.running = True
    provider = _provider(docker, repo=repo, module=module)

    result = provider.run_action("save_backend", {"backend_url": "localhost:9999"})
    assert result["ok"] is True
    assert result["backend_url"] == "http://localhost:9999"
    assert repo.get_app_setting("ollama_base_url") == "http://localhost:9999"


# ---------------------------------------------------------------------------
# docker_card status tile tests for various states
# ---------------------------------------------------------------------------


def test_ollama_docker_card_status_tile_container_missing(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": False})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _Docker()
    docker.exists = False
    docker.running = False
    provider = _provider(docker, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    status_tile = next(m for m in card["meta"] if m["label"] == "Status")
    assert status_tile["value"]["label"] == "Not created"
    assert status_tile["value"]["tone"] == "warning"


def test_ollama_docker_card_status_tile_docker_unavailable(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    provider = _provider(None, module=module)

    payload = provider.get_tab_payload()
    card = _docker_card_from_tab_payload(payload)

    status_tile = next(m for m in card["meta"] if m["label"] == "Status")
    assert status_tile["value"]["label"] == "Docker unavailable"
    assert status_tile["value"]["tone"] == "error"


# ---------------------------------------------------------------------------
# cloud usage section tests
# ---------------------------------------------------------------------------

def _cloud_section_from_tab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload["schema"]["pages"][0]["sections"]
    for section in sections:
        if section.get("id") == "cloud_usage":
            return section
    raise AssertionError("cloud_usage section not found in tab payload")


def test_ollama_tab_payload_cloud_usage_not_configured(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    provider = _provider(None, repo=_Repo(), module=module)

    payload = provider.get_tab_payload()
    section = _cloud_section_from_tab_payload(payload)

    assert len(section["components"]) == 1
    assert section["components"][0]["key"] == "cloud_usage_status"
    assert "Not configured" in section["components"][0]["value"]


def test_ollama_tab_payload_cloud_usage_with_key(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    repo = _Repo()
    repo.set_app_setting("ollama_provider_ollama_api_key", "test-key")
    monkeypatch.setattr(
        module,
        "fetch_cloud_usage",
        lambda _repo: {
            "configured": True,
            "plan": "pro",
            "session_usage": "8%",
            "weekly_usage": "35%",
            "activity_cost": "0.00000",
            "session_models": "glm-5.3-flash: 133",
            "weekly_models": "glm-5.3-flash: 2335",
        },
    )
    provider = _provider(None, repo=repo, module=module)

    payload = provider.get_tab_payload()
    section = _cloud_section_from_tab_payload(payload)

    by_key = {c["key"]: c for c in section["components"]}
    assert by_key["cloud_usage_plan"]["value"] == "pro"
    assert by_key["cloud_usage_session"]["value"] == "8%"
    assert by_key["cloud_usage_weekly"]["value"] == "35%"
    assert by_key["cloud_usage_cost"]["value"] == "0.00000"
    assert by_key["cloud_usage_session_models"]["value"] == "glm-5.3-flash: 133"
    assert by_key["cloud_usage_weekly_models"]["value"] == "glm-5.3-flash: 2335"
    assert "cloud_usage_error" not in by_key


def test_ollama_tab_payload_cloud_usage_error_does_not_break_payload(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": True})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    repo = _Repo()
    repo.set_app_setting("ollama_provider_ollama_api_key", "test-key")
    monkeypatch.setattr(
        module,
        "fetch_cloud_usage",
        lambda _repo: {"configured": True, "error": "Invalid or revoked API key"},
    )
    provider = _provider(None, repo=repo, module=module)

    payload = provider.get_tab_payload()
    section = _cloud_section_from_tab_payload(payload)

    by_key = {c["key"]: c for c in section["components"]}
    assert by_key["cloud_usage_error"]["value"] == "Invalid or revoked API key"
    assert by_key["cloud_usage_plan"]["value"] == "—"
