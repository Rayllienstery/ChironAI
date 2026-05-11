from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_interactor import ProviderHostContext


def _load_ollama_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "ollama-provider" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_ollama_provider_backend", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ChatClient:
    _url = "http://localhost:11434/api/chat"
    _model = "llama3.2"


class _DockerRuntime:
    def __init__(self) -> None:
        self.ensure_spec = None
        self.stopped = ""

    def ensure_container(self, spec: Any) -> dict[str, Any]:
        self.ensure_spec = spec
        return {"ok": True, "container": spec.name, "image": spec.image}

    def wait_http(self, url: str, *, path: str, timeout: float, interval: float) -> dict[str, Any]:
        return {"ok": True, "url": f"{url.rstrip('/')}{path}", "status_code": 200}

    def stop_container(self, container: str) -> dict[str, Any]:
        self.stopped = container
        return {"ok": True, "container": container, "message": "stopped"}


def _provider(docker_runtime: Any | None):
    module = _load_ollama_provider_module()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(
        project_root=root,
        get_settings_repository=lambda: None,
        chat_client=_ChatClient(),
        docker_runtime=docker_runtime,
    )
    manifest = SimpleNamespace(
        id="ollama-provider",
        title="Ollama Provider",
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
