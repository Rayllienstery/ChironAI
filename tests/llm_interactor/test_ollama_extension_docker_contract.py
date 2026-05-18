from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_interactor import LLMRequest, ProviderHostContext
from llm_interactor.discovery import load_manifest_from_dir, validate_extension_backend_docker_policy


def _load_ollama_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "ollama-provider" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_ollama_provider_backend", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundled_ollama_manifest_declares_expected_capabilities() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "extensions" / "bundled" / "ollama-provider" / "chironai-extension.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["id"] == "ollama-provider"
    assert manifest["title"] == "Ollama"
    capabilities = manifest.get("capabilities") or {}
    for key in (
        "chat",
        "embed",
        "rerank",
        "streaming",
        "tools",
        "vision",
        "model_listing",
        "health_check",
        "tab_ui",
        "service_actions",
    ):
        assert capabilities.get(key) is True


def test_bundled_ollama_provider_surface_covers_migration_baseline() -> None:
    provider = _provider(_DockerRuntime())
    descriptor = provider.describe()

    assert descriptor.id == "ollama"
    assert descriptor.extension_id == "ollama-provider"
    assert descriptor.title == "Ollama"
    assert descriptor.capabilities.chat is True
    assert descriptor.capabilities.embed is True
    assert descriptor.capabilities.rerank is True
    assert descriptor.capabilities.streaming is True
    assert descriptor.capabilities.tools is True
    assert descriptor.capabilities.vision is True
    assert descriptor.capabilities.model_listing is True
    assert descriptor.capabilities.health_check is True
    assert descriptor.capabilities.tab_ui is True
    assert descriptor.capabilities.service_actions is True
    for name in (
        "invoke",
        "stream_invoke",
        "list_models",
        "health_check",
        "get_tab_payload",
        "run_action",
        "_invoke_embed",
        "_invoke_rerank",
        "_invoke_raw_ollama",
        "_stream_raw_ollama",
    ):
        assert callable(getattr(provider, name))


def test_ollama_extension_http_helper_is_self_contained() -> None:
    root = Path(__file__).resolve().parents[2]
    http_path = root / "extensions" / "bundled" / "ollama-provider" / "backend" / "ollama_http.py"
    text = http_path.read_text(encoding="utf-8")

    assert not re.search(r"^\s*(?:from|import)\s+infrastructure\b", text, re.MULTILINE)
    assert not re.search(r"^\s*(?:from|import)\s+api\b", text, re.MULTILINE)
    assert not re.search(r"^\s*(?:from|import)\s+rag_service\b", text, re.MULTILINE)


def test_bundled_ollama_provider_backend_satisfies_docker_policy() -> None:
    root = Path(__file__).resolve().parents[2]
    source_dir = root / "extensions" / "bundled" / "ollama-provider"
    manifest = load_manifest_from_dir(source_dir)

    assert manifest.backend is not None
    validate_extension_backend_docker_policy(source_dir, manifest.backend.entrypoint)


class _ChatClient:
    _url = "http://localhost:11434/api/chat"
    _model = "llama3.2"


class _DockerRuntime:
    def __init__(self) -> None:
        self.ensure_spec = None
        self.stopped = ""
        self.exists = True
        self.running = False

    def ensure_container(self, spec: Any) -> dict[str, Any]:
        self.ensure_spec = spec
        return {"ok": True, "container": spec.name, "image": spec.image}

    def wait_http(self, url: str, *, path: str, timeout: float, interval: float) -> dict[str, Any]:
        return {"ok": True, "url": f"{url.rstrip('/')}{path}", "status_code": 200}

    def stop_container(self, container: str) -> dict[str, Any]:
        self.stopped = container
        return {"ok": True, "container": container, "message": "stopped"}

    def inspect_container(self, container: str) -> Any:
        return SimpleNamespace(exists=self.exists, running=self.running, name=container)


class _Repo:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_app_setting(self, key: str) -> str:
        return self.values.get(key, "")

    def set_app_setting(self, key: str, value: str) -> None:
        self.values[key] = value


def _diagnostics_from_tab_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload["schema"]["pages"][0]["sections"]
    for sec in sections:
        if sec.get("id") == "diagnostics":
            for c in sec.get("components") or []:
                if c.get("key") == "provider_diagnostics":
                    return c["value"]
    raise AssertionError("diagnostics not found in tab payload")


def _provider(docker_runtime: Any | None, *, repo: Any | None = None, module: Any | None = None):
    module = module or _load_ollama_provider_module()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(
        project_root=root,
        get_settings_repository=lambda: repo or _Repo(),
        chat_client=_ChatClient(),
        docker_runtime=docker_runtime,
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


def test_ollama_extension_start_stop_use_docker_runtime() -> None:
    docker = _DockerRuntime()
    provider = _provider(docker)

    started = provider.run_action("start_service", {})
    stopped = provider.run_action("stop_service", {})

    assert started["ok"] is True
    assert docker.ensure_spec.name == "chironai-ollama"
    assert docker.ensure_spec.image == "ollama/ollama:latest"
    assert docker.ensure_spec.ports == ["11434:11434"]
    assert docker.ensure_spec.volumes == ["ollama_models:/root/.ollama"]
    assert stopped["ok"] is True
    assert docker.stopped == "chironai-ollama"


def test_ollama_extension_reports_missing_docker_runtime() -> None:
    provider = _provider(None)

    started = provider.run_action("start_service", {})
    stopped = provider.run_action("stop_service", {})

    assert started["ok"] is False
    assert started["message"] == "Docker runtime is unavailable"
    assert stopped["ok"] is False
    assert stopped["message"] == "Docker runtime is unavailable"


def test_ollama_extension_model_actions_have_stable_response_shapes(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    repo = _Repo()
    shown: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []

    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": [{"name": "tiny-model:latest"}]})

    def fake_show(**kwargs):
        shown.append(dict(kwargs))
        return {"model_info": {"general.architecture": "llama"}, "capabilities": ["completion"]}

    def fake_delete(**kwargs):
        deleted.append(dict(kwargs))
        return {"deleted": True}

    monkeypatch.setattr(module, "invoke_show", fake_show)
    monkeypatch.setattr(module, "invoke_delete", fake_delete)
    monkeypatch.setattr(
        module,
        "iter_pull_objects",
        lambda **_: iter([{"status": "pulling"}, {"status": "success", "completed": 1}]),
    )

    provider = _provider(_DockerRuntime(), repo=repo, module=module)

    shown_result = provider.run_action("show_model", {"selected_model": "tiny-model:latest"})
    hidden_result = provider.run_action("hide_model", {"selected_model": "tiny-model:latest"})
    unhidden_result = provider.run_action("unhide_model", {"selected_model": "tiny-model:latest"})
    deleted_result = provider.run_action("delete_model", {"selected_model": "tiny-model:latest"})
    pulled_result = provider.run_action("pull_model", {"pull_model_name": "tiny-model:latest"})
    refreshed_result = provider.run_action("refresh", {})

    assert shown_result["ok"] is True
    assert shown_result["message"] == "Loaded details for tiny-model:latest"
    assert shown_result["details"]["model_info"]["general.architecture"] == "llama"
    assert hidden_result["ok"] is True
    assert hidden_result["message"] == "Hidden tiny-model:latest"
    assert hidden_result["details"] == {"model": "tiny-model:latest"}
    assert hidden_result["hidden_model_ids"] == ["tiny-model:latest"]
    assert unhidden_result["ok"] is True
    assert unhidden_result["message"] == "Unhid tiny-model:latest"
    assert unhidden_result["details"] == {"model": "tiny-model:latest"}
    assert unhidden_result["hidden_model_ids"] == []
    assert deleted_result == {"ok": True, "message": "Deleted tiny-model:latest", "details": {}}
    assert pulled_result["ok"] is True
    assert pulled_result["message"] == "Pull completed for tiny-model:latest"
    assert pulled_result["details"] == {"status": "success", "completed": 1}
    assert refreshed_result == {"ok": True, "message": "Refreshed", "details": {}}
    assert shown[0]["name"] == "tiny-model:latest"
    assert deleted[0]["name"] == "tiny-model:latest"


def test_ollama_extension_raw_ollama_operations_delegate_to_provider_http(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    raw_calls: list[dict[str, Any]] = []
    stream_calls: list[dict[str, Any]] = []

    def fake_raw_json(**kwargs):
        raw_calls.append(dict(kwargs))
        return {"echo": kwargs.get("body"), "segment": kwargs.get("api_segment")}

    def fake_raw_lines(**kwargs):
        stream_calls.append(dict(kwargs))
        yield '{"done":false}'
        yield '{"done":true}'

    monkeypatch.setattr(module, "invoke_raw_json", fake_raw_json)
    monkeypatch.setattr(module, "iter_raw_lines", fake_raw_lines)

    provider = _provider(_DockerRuntime(), repo=_Repo(), module=module)
    response = provider.invoke(
        LLMRequest(
            provider_id="ollama",
            model="tiny-model:latest",
            operation="raw_ollama",
            body={"model": "tiny-model:latest", "prompt": "hi", "stream": False},
            metadata={"api_segment": "generate", "method": "POST", "headers": {"Authorization": "Bearer x"}},
        )
    )
    events = list(
        provider.stream_invoke(
            LLMRequest(
                provider_id="ollama",
                model="tiny-model:latest",
                operation="raw_ollama",
                body={"model": "tiny-model:latest", "messages": [], "stream": True},
                stream=True,
                metadata={"api_segment": "chat"},
            )
        )
    )

    assert response.raw == {
        "echo": {"model": "tiny-model:latest", "prompt": "hi", "stream": False},
        "segment": "generate",
    }
    assert raw_calls[0]["api_segment"] == "generate"
    assert raw_calls[0]["headers"] == {"Authorization": "Bearer x"}
    assert stream_calls[0]["api_segment"] == "chat"
    assert [event.type for event in events] == ["raw_line", "raw_line"]
    assert [event.data for event in events] == ['{"done":false}', '{"done":true}']


def test_ollama_extension_tab_reports_missing_container(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": False})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _DockerRuntime()
    docker.exists = False
    provider = _provider(docker, repo=_Repo(), module=module)

    payload = provider.get_tab_payload()
    diagnostics = _diagnostics_from_tab_payload(payload)

    assert diagnostics["health"]["status"] == "container_missing"
    assert diagnostics["docker"]["exists"] is False
    assert diagnostics["docker"]["action_hint"] == "download"
    assert "does not exist" in diagnostics["health"]["message"]


def test_ollama_extension_tab_reports_stopped_container(monkeypatch: Any) -> None:
    module = _load_ollama_provider_module()
    monkeypatch.setattr(module, "invoke_ping", lambda **_: {"ok": False})
    monkeypatch.setattr(module, "invoke_tags", lambda **_: {"models": []})

    docker = _DockerRuntime()
    docker.exists = True
    docker.running = False
    provider = _provider(docker, repo=_Repo(), module=module)

    payload = provider.get_tab_payload()
    diagnostics = _diagnostics_from_tab_payload(payload)

    assert diagnostics["health"]["status"] == "container_stopped"
    assert diagnostics["docker"]["exists"] is True
    assert diagnostics["docker"]["running"] is False
    assert diagnostics["docker"]["action_hint"] == "start"
    assert "exists but is stopped" in diagnostics["health"]["message"]
