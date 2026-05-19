from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from extensions_sandbox import ExtensionWorkerClient, ExtensionWorkerTimeout
from llm_interactor import LLMRequest, ProviderHostContext
from llm_interactor.discovery import discover_extensions, load_manifest_from_dir


class _Repo:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_app_setting(self, key: str):
        return self.data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.data[key] = str(value)


class _Chat:
    _url = "http://localhost:11434/api/chat"
    _model = "tiny-model:latest"

    def chat(self, messages, model, **kwargs):
        return f"chat:{model}:{messages[-1]['content']}"

    def chat_api(self, body):
        return {"message": {"content": "api"}, "done": True}

    def iter_chat_api_stream_events(self, body):
        yield ("content_delta", "stream")
        yield ("done", {"done": True})


def _write_extension(root: Path, *, provider_py: str) -> Path:
    ext = root / "sandbox-ext"
    backend = ext / "backend"
    backend.mkdir(parents=True)
    (backend / "provider.py").write_text(provider_py, encoding="utf-8")
    (ext / "chironai-extension.json").write_text(
        json.dumps(
            {
                "id": "sandbox-ext",
                "version": "1.0.0",
                "api_version": "1",
                "type": "llm_provider",
                "title": "Sandbox",
                "backend": {"entrypoint": "backend.provider:create_provider"},
                "capabilities": {"chat": True, "tab_ui": True, "service_actions": True},
            }
        ),
        encoding="utf-8",
    )
    return ext


def _host(root: Path, repo: _Repo | None = None) -> ProviderHostContext:
    return ProviderHostContext(
        project_root=Path(__file__).resolve().parents[2],
        get_settings_repository=lambda: repo or _Repo(),
        chat_client=_Chat(),
        docker_runtime=None,
    )


PROVIDER = """
from collections.abc import Iterator
from llm_interactor.contracts import (
    LLMResponse,
    LLMStreamEvent,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
)

class Provider:
    def __init__(self, host_context, manifest):
        self._host = host_context
        self._manifest = manifest

    def describe(self):
        return ProviderDescriptor(
            id="sandbox",
            extension_id=self._manifest.id,
            title="Sandbox",
            capabilities=ProviderCapabilities(chat=True, streaming=True, tab_ui=True, service_actions=True),
            metadata={"url": getattr(self._host.chat_client, "_url", "")},
        )

    def list_models(self):
        return [ModelDescriptor(id="tiny", provider_id="sandbox", label="Tiny")]

    def health_check(self):
        return ProviderHealth(provider_id="sandbox", ok=True, status="ok")

    def invoke(self, request):
        repo = self._host.get_settings_repository()
        repo.set_app_setting("last_model", request.model)
        text = self._host.chat_client.chat(request.messages, request.model)
        return LLMResponse(provider_id="sandbox", model=request.model, text=text)

    def stream_invoke(self, request):
        yield LLMStreamEvent(provider_id="sandbox", model=request.model, type="content_delta", data="a")
        yield LLMStreamEvent(provider_id="sandbox", model=request.model, type="done", data={})

    def get_tab_descriptor(self):
        return {"id": "sandbox", "title": "Sandbox", "frame": {}}

    def get_tab_payload(self):
        return {"state": {"last_model": self._host.get_settings_repository().get_app_setting("last_model") or ""}}

    def run_action(self, action_id, payload):
        if action_id == "sleep":
            import time
            time.sleep(2)
        return {"ok": True, "action_id": action_id, "payload": payload}

def create_provider(host_context, manifest):
    return Provider(host_context, manifest)
"""


def test_sandboxed_extension_provider_round_trips_runtime_calls(tmp_path: Path) -> None:
    repo = _Repo()
    ext = _write_extension(tmp_path, provider_py=PROVIDER)
    report = discover_extensions([ext], host_context=_host(tmp_path, repo))

    assert report.failed == []
    loaded = report.loaded[0]
    provider = loaded.provider
    assert loaded.sandboxed is True
    assert provider.describe().id == "sandbox"
    assert provider.list_models()[0].id == "tiny"
    response = provider.invoke(LLMRequest(model="tiny", messages=[{"role": "user", "content": "hi"}]))
    events = list(provider.stream_invoke(LLMRequest(model="tiny")))
    assert response.text == "chat:tiny:hi"
    assert repo.get_app_setting("last_model") == "tiny"
    assert events[-1].type == "done"
    assert provider.get_tab_descriptor()["id"] == "sandbox"
    assert provider.get_tab_payload()["state"]["last_model"] == "tiny"
    assert provider.run_action("echo", {"x": 1})["payload"] == {"x": 1}
    provider.close()


def test_worker_client_times_out_slow_calls(tmp_path: Path) -> None:
    ext = _write_extension(tmp_path, provider_py=PROVIDER)
    manifest = load_manifest_from_dir(ext)
    assert manifest.backend is not None
    client = ExtensionWorkerClient(
        source_dir=ext,
        entrypoint=manifest.backend.entrypoint,
        manifest=manifest,
        project_root=Path(__file__).resolve().parents[2],
        host_context=_host(tmp_path),
        timeout_sec=1.0,
    )
    try:
        with pytest.raises(ExtensionWorkerTimeout):
            client.call("run_action", {"action_id": "sleep", "payload": {}}, timeout_sec=0.1)
    finally:
        client.close()


def test_worker_initialization_failure_reports_failed_extension(tmp_path: Path) -> None:
    ext = _write_extension(
        tmp_path,
        provider_py="""
def create_provider(host_context, manifest):
    raise RuntimeError("boom")
""",
    )

    report = discover_extensions([ext], host_context=_host(tmp_path))

    assert report.loaded == []
    assert report.failed[0].extension_id == "sandbox-ext"
    assert "boom" in report.failed[0].error
    assert report.failed[0].sandbox_error
