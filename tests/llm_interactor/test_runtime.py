from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from extensions_backend import ExtensionBlocklistPolicy
from llm_interactor import (
    EXTENSION_API_VERSION,
    ExtensionManager,
    ExtensionManifest,
    ExtensionRegistryClient,
    ExtensionsRepository,
    InstalledExtensionRecord,
    LLMRequest,
    LLMResponse,
    LLMRuntime,
    LLMStreamEvent,
    LoadedExtension,
    ModelDescriptor,
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderHealth,
    ProviderHostContext,
    ProviderRegistry,
    RuntimeBackedChatClient,
)


class _StubProvider:
    def __init__(self, provider_id: str = "stub") -> None:
        self._provider_id = provider_id

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id=self._provider_id,
            extension_id="stub-ext",
            title="Stub",
            capabilities=ProviderCapabilities(),
        )

    def list_models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                id="model-a",
                provider_id=self._provider_id,
                label="Model A",
                capabilities=ProviderCapabilities(),
            )
        ]

    def invoke(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(provider_id=self._provider_id, model=request.model, text="ok")

    def stream_invoke(self, request: LLMRequest):
        yield from ()

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self._provider_id, ok=True, status="ok")


class _SandboxDiagnosticsProvider(_StubProvider):
    sandboxed = True

    def __init__(self) -> None:
        super().__init__("sandbox-diag")
        self.sandbox_pid = 111
        self.sandbox_status = "ready"
        self.sandbox_error = ""
        self.sandbox_last_error = ""
        self.sandbox_restart_count = 0
        self.sandbox_blocked = False
        self.sandbox_manual_restart_required = False

    def restart_sandbox(self) -> None:
        self.sandbox_pid = 222
        self.sandbox_status = "ready"
        self.sandbox_restart_count += 1
        self.sandbox_blocked = False
        self.sandbox_manual_restart_required = False

    def kill_sandbox(self) -> None:
        self.sandbox_pid = None
        self.sandbox_status = "manual_stop"
        self.sandbox_manual_restart_required = True

    def get_tab_descriptor(self, *, runtime=None) -> dict[str, object]:
        if self.sandbox_status == "manual_stop":
            raise RuntimeError("extension worker is stopped until manual restart")
        return {"id": "sandbox-ext", "title": "Sandbox", "frame": {}}


class _FakeCompletedProcess:
    def __init__(self, stdout: str = "{}", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _FakeOllamaChatClient:
    def __init__(self) -> None:
        self._url = "http://localhost:11434/api/chat"
        self._model = "tiny-model:latest"
        self.chat_calls: list[dict[str, object]] = []

    def chat(
        self,
        messages: list[dict[str, object]],
        model: str,
        stream: bool = False,
        options: dict[str, object] | None = None,
        think: bool | str | None = None,
    ) -> str:
        self.chat_calls.append(
            {
                "messages": messages,
                "model": model,
                "stream": stream,
                "options": dict(options or {}),
                "think": think,
            }
        )
        return f"reply:{model}:{messages[-1]['content']}"

    def chat_api(self, body: dict[str, object]) -> dict[str, object]:
        return {
            "model": body.get("model"),
            "message": {"role": "assistant", "content": "api reply"},
            "done": True,
            "eval_count": 3,
        }

    def iter_chat_api_stream_events(self, body: dict[str, object]):
        yield ("thinking_delta", "hmm")
        yield ("content_delta", f"stream:{body.get('model')}")
        yield ("done", {"done": True, "total_duration": 42})


class _MemorySettingsRepo:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_app_setting(self, key: str):
        return self.data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.data[key] = value


def _write_minimal_extension(
    source: Path,
    *,
    ext_id: str,
    version: str = "1.0.0",
    unsafe: bool = False,
    capabilities: dict[str, object] | None = None,
) -> None:
    backend = source / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": ext_id,
        "version": version,
        "api_version": EXTENSION_API_VERSION,
        "type": "ui_extension",
        "title": ext_id,
        "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
        "capabilities": dict(capabilities or {"tab_ui": True}),
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    (source / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    if unsafe:
        provider_source = (
            "import subprocess\n"
            "def create_provider(host_context, manifest):\n"
            "    subprocess.run(['cmd.exe', '/c', 'whoami'], check=False)\n"
            "    return object()\n"
        )
    else:
        provider_source = "def create_provider(host_context, manifest):\n    return object()\n"
    (backend / "provider.py").write_text(provider_source, encoding="utf-8")


def test_runtime_without_provider_raises_clear_error() -> None:
    runtime = LLMRuntime(ProviderRegistry())
    with pytest.raises(RuntimeError, match="no provider configured"):
        runtime.invoke(LLMRequest(model="m"))


def test_provider_registry_rejects_duplicate_ids() -> None:
    registry = ProviderRegistry()
    registry.register(_StubProvider("dup"))
    with pytest.raises(ValueError, match="duplicate provider id"):
        registry.register(_StubProvider("dup"))


def test_runtime_backed_chat_client_preserves_proxy_methods() -> None:
    class _Runtime:
        def __init__(self) -> None:
            self.requests: list[LLMRequest] = []

        def invoke(self, request: LLMRequest) -> LLMResponse:
            self.requests.append(request)
            if request.operation == "chat_api":
                return LLMResponse(
                    provider_id="ollama",
                    model=request.model,
                    text="raw text",
                    raw={"message": {"content": "raw text"}, "done": True},
                )
            return LLMResponse(provider_id="ollama", model=request.model, text="hello")

        def stream_invoke(self, request: LLMRequest):
            self.requests.append(request)
            yield LLMStreamEvent(provider_id="ollama", model=request.model, type="thinking_delta", data="think")
            yield LLMStreamEvent(provider_id="ollama", model=request.model, type="content_delta", data=" part")
            yield LLMStreamEvent(provider_id="ollama", model=request.model, type="done", data={"done": True})

    runtime = _Runtime()
    client = RuntimeBackedChatClient(  # type: ignore[arg-type]
        runtime,
        provider_id="ollama",
        default_options={"temperature": 0.1},
    )

    assert client.chat([{"role": "user", "content": "hi"}], "tiny") == "hello"
    assert client.chat([{"role": "user", "content": "hi"}], "tiny", stream=True) == "think part"
    assert list(client.stream_chat([{"role": "user", "content": "hi"}], "tiny")) == [" part"]
    assert client.chat_api({"model": "tiny"}) == {"message": {"content": "raw text"}, "done": True}
    assert client.chat_api_stream_final({"model": "tiny", "stream": True}) == {
        "message": {"content": "raw text"},
        "done": True,
    }
    assert list(client.iter_chat_api_stream_events({"model": "tiny"}))[-1] == ("done", {"done": True})
    assert list(client.iter_chat_api_stream_openai_parts({"model": "tiny"})) == [
        ("content", "think"),
        ("content", " part"),
    ]
    assert runtime.requests[0].operation == "chat"
    assert runtime.requests[0].options == {"temperature": 0.1}
    assert any(request.operation == "chat_api_stream_events" for request in runtime.requests)


def test_extension_manager_bootstraps_builtin_ollama(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
    )
    bootstrap = manager.bootstrap_runtime()
    installed = manager.installed_extensions()
    assert bootstrap.runtime is not None
    assert any(item["id"] == "ollama-provider" for item in installed)
    assert any(item["id"] == "ollama-provider" and item["title"] == "Ollama" for item in installed)
    assert any(item["id"] == "open-webui" for item in installed)
    assert any(item["id"] == "codex-launcher" for item in installed)
    descriptors = bootstrap.runtime.registry.descriptors()
    assert any(desc.id == "ollama" and desc.title == "Ollama" for desc in descriptors), {
        "descriptors": [(desc.id, desc.title) for desc in descriptors],
        "failed": [(item.extension_id, item.error) for item in bootstrap.failed],
        "loaded": [(item.manifest.id, item.manifest.type) for item in bootstrap.loaded],
    }
    catalog = manager.provider_catalog(runtime=bootstrap.runtime, capability="chat")
    assert any(row["provider_id"] == "ollama" and row["title"] == "Ollama" for row in catalog["providers"])
    tabs = manager.extension_tabs(runtime=bootstrap.runtime)
    assert any(tab["id"] == "open-webui" and "status" in tab for tab in tabs)
    assert any(tab["id"] == "ollama" and tab.get("frame", {}).get("id") == "ollama-runtime-frame" for tab in tabs)
    assert any(tab["id"] == "codex" and tab.get("extension_id") == "codex-launcher" for tab in tabs)
    assert any(tab["id"] == "open-webui" and tab.get("frame") == {} for tab in tabs)
    assert any(tab["id"] == "ollama" and tab.get("icon_url", "").endswith("/icons/ollama-light.svg") for tab in tabs)


def test_extension_lifecycle_reload_failure_is_reported_without_crashing_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
    )
    manager.ensure_bundled_installed()
    stable_runtime = object()
    manager._runtime = stable_runtime

    def _fail_reload():
        raise RuntimeError("reload boom")

    monkeypatch.setattr(manager, "bootstrap_runtime", _fail_reload)

    result = manager.disable("ollama-provider")
    installed = {item["id"]: item for item in manager.installed_extensions()}

    assert result["reload_status"] == "failed"
    assert result["restart_required"] is True
    assert "reload boom" in result["reload_error"]
    assert manager.runtime is stable_runtime
    assert installed["ollama-provider"]["enabled"] is False


def test_ollama_provider_runtime_invocation_streaming_and_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    def _fake_run(cmd, input=None, capture_output=True, text=True, timeout=None, env=None):
        _ = capture_output
        joined = " ".join(str(part) for part in cmd)
        if " ping " in f" {joined} ":
            return _FakeCompletedProcess('{"ok": true, "status_code": 200}')
        if " tags " in f" {joined} ":
            return _FakeCompletedProcess(
                '{"models": [{"name": "tiny-model:latest", "size": 12, "modified_at": "2026-01-01T00:00:00Z"}]}'
            )
        raise AssertionError(f"unexpected subprocess call: {joined}")

    monkeypatch.setattr("subprocess.run", _fake_run)

    repo = _Repo()
    chat_client = _FakeOllamaChatClient()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=chat_client)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
        use_sandbox=False,
    )
    bootstrap = manager.bootstrap_runtime()
    provider = bootstrap.registry.get("ollama")
    assert provider is not None
    provider_module = sys.modules[provider.__class__.__module__]
    provider_module._CACHE.clear()
    monkeypatch.setattr(
        provider_module,
        "invoke_tags",
        lambda *, base_url, timeout: {
            "models": [{"name": "tiny-model:latest", "size": 12, "modified_at": "2026-01-01T00:00:00Z"}]
        },
    )
    monkeypatch.setattr(provider_module, "invoke_ping", lambda *, base_url, timeout: {"ok": True, "status_code": 200})
    monkeypatch.setattr(
        provider.__class__,
        "_invoke_chat_http",
        lambda self, body, timeout=600.0: {
            "model": body.get("model"),
            "message": {
                "role": "assistant",
                "content": f"reply:{body.get('model')}:{body.get('messages', [{}])[-1].get('content')}",
            },
            "done": True,
            "eval_count": 3,
        },
    )
    monkeypatch.setattr(
        provider.__class__,
        "_iter_ollama_chat_http_events",
        lambda self, body: iter(
            [
                ("thinking_delta", "hmm"),
                ("content_delta", f"stream:{body.get('model')}"),
                ("done", {"done": True, "total_duration": 42}),
            ]
        ),
    )
    manager._provider_rows_cache = []

    response = bootstrap.runtime.invoke(
        LLMRequest(
            model="tiny-model:latest",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    events = list(
        bootstrap.runtime.stream_invoke(
            LLMRequest(
                model="tiny-model:latest",
                operation="chat_api_stream_events",
                body={"model": "tiny-model:latest", "messages": [], "stream": True},
                stream=True,
            )
        )
    )
    catalog = manager.provider_catalog(runtime=bootstrap.runtime, capability="chat")

    assert response.provider_id == "ollama"
    assert response.text == "reply:tiny-model:latest:hello"
    assert [(event.type, event.data) for event in events] == [
        ("thinking_delta", "hmm"),
        ("content_delta", "stream:tiny-model:latest"),
        ("done", {"done": True, "total_duration": 42}),
    ]
    model = next(item for item in catalog["models"] if item["id"] == "tiny-model:latest")
    assert model["provider_id"] == "ollama"
    assert model["provider_title"] == "Ollama"
    assert model["metadata"]["size"] == 12


def test_provider_host_context_accepts_docker_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    docker_runtime = object()
    host = ProviderHostContext(
        project_root=root,
        get_settings_repository=lambda: None,
        chat_client=None,
        docker_runtime=docker_runtime,
    )

    assert host.docker_runtime is docker_runtime


def test_extension_manager_exposes_and_controls_sandbox_diagnostics(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )
    ExtensionsRepository(repo).save_records(
        [
            InstalledExtensionRecord(
                id="sandbox-ext",
                version="1.0.0",
                enabled=True,
                installed=True,
                title="Sandbox",
            )
        ]
    )
    manifest = ExtensionManifest(
        id="sandbox-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="llm_provider",
        title="Sandbox",
    )
    provider = _SandboxDiagnosticsProvider()
    manager._loaded = [
        LoadedExtension(
            manifest=manifest,
            source_dir=tmp_path / "installed" / "sandbox-ext" / "1.0.0",
            provider=provider,
            sandboxed=True,
        )
    ]

    installed = manager.installed_extensions()[0]
    assert installed["sandbox_pid"] == 111
    assert installed["sandbox_status"] == "ready"
    assert installed["sandbox_restart_count"] == 0
    assert installed["sandbox_can_restart"] is True
    assert installed["sandbox_can_kill"] is True

    killed = manager.kill_extension_sandbox("sandbox-ext")
    assert killed["sandbox_status"] == "manual_stop"
    assert killed["sandbox_pid"] is None
    assert manager.installed_extensions()[0]["status"] == "failed"
    assert manager.provider_rows(LLMRuntime(ProviderRegistry())) == []
    tabs = manager.extension_tabs(runtime=LLMRuntime(ProviderRegistry()))
    assert tabs[0]["status"]["runtime"] == "manual_stop"

    restarted = manager.restart_extension_sandbox("sandbox-ext")
    assert restarted["sandbox_pid"] == 222
    assert restarted["sandbox_restart_count"] == 1
    assert manager.installed_extensions()[0]["status"] == "loaded"


def test_extension_manager_exposes_manifest_tabs_before_runtime_ready(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
    )

    manager.ensure_bundled_installed()
    tabs = manager.extension_tabs(runtime=None)

    assert manager.runtime_status == "not_started"
    assert any(tab["id"] == "ollama" and tab["status"]["runtime"] == "not_started" for tab in tabs)
    assert any(tab["id"] == "open-webui" and tab.get("icon_url", "").endswith("/icons/open-webui-light.svg") for tab in tabs)
    assert any(tab["id"] == "codex" and tab.get("icon_url", "").endswith("/icons/codex-light.svg") for tab in tabs)


def test_extension_tabs_timeout_slow_provider_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_interactor.manager as manager_module

    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            pass

    class _SlowProvider(_StubProvider):
        def get_tab_descriptor(self, *, runtime=None):
            time.sleep(1.0)
            return {"id": "slow", "title": "Slow"}

    monkeypatch.setattr(manager_module, "_EXTENSION_TAB_DESCRIPTOR_TIMEOUT_SEC", 0.05)

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    manifest = ExtensionManifest(
        id="slow-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="llm_provider",
        title="Slow",
    )
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )
    manager._loaded = [
        LoadedExtension(manifest=manifest, source_dir=tmp_path / "slow-ext", provider=_SlowProvider())
    ]

    started = time.perf_counter()
    tabs = manager.extension_tabs(runtime=LLMRuntime(ProviderRegistry()))
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert tabs[0]["id"] == "slow-ext"
    assert tabs[0]["load_state"]["status"] == "missing"

    deadline = time.time() + 1.0
    while time.time() < deadline:
        tabs = manager.extension_tabs(runtime=LLMRuntime(ProviderRegistry()))
        if tabs[0]["load_state"]["status"] == "timeout":
            break
        time.sleep(0.02)

    assert tabs[0]["load_state"]["status"] == "timeout"
    assert tabs[0]["status"]["tone"] == "error"
    assert "tab descriptor timed out" in tabs[0]["status"]["message"]


def test_extension_tab_payload_timeout_keeps_loading_payload_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_interactor.manager as manager_module

    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            pass

    class _SlowProvider(_StubProvider):
        def get_tab_payload(self, *, runtime=None):
            time.sleep(1.0)
            return {"schema": {}}

    monkeypatch.setattr(manager_module, "_EXTENSION_TAB_PAYLOAD_TIMEOUT_SEC", 0.05)

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    manifest = ExtensionManifest(
        id="slow-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="llm_provider",
        title="Slow",
    )
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )
    manager._loaded = [
        LoadedExtension(manifest=manifest, source_dir=tmp_path / "slow-ext", provider=_SlowProvider())
    ]

    payload = manager.extension_tab_payload("slow-ext", runtime=LLMRuntime(ProviderRegistry()))

    assert payload["extension_id"] == "slow-ext"
    assert payload["load_state"]["status"] == "refreshing"

    deadline = time.time() + 1.0
    while time.time() < deadline:
        payload = manager.extension_tab_payload("slow-ext", runtime=LLMRuntime(ProviderRegistry()))
        if payload["load_state"]["status"] == "timeout":
            break
        time.sleep(0.02)

    assert payload["load_state"]["status"] == "timeout"
    assert payload["load_state"]["error"]
    assert payload["status"]["tone"] == "loading"
    assert payload["schema"]["pages"] == []

    retry = manager.refresh_extension_tab("slow-ext", runtime=LLMRuntime(ProviderRegistry()))
    assert retry["load_state"]["status"] == "refreshing"
    assert retry["job_id"]


def test_extension_tab_refresh_dedupes_background_job(tmp_path: Path) -> None:
    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            pass

    class _SlowPayloadProvider(_StubProvider):
        def __init__(self) -> None:
            super().__init__("slow")
            self.calls = 0

        def get_tab_descriptor(self, *, runtime=None):
            return {"id": "slow-ext", "title": "Slow"}

        def get_tab_payload(self, *, runtime=None):
            self.calls += 1
            time.sleep(0.1)
            return {"schema": {"pages": [{"id": "main", "sections": []}]}}

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    manifest = ExtensionManifest(
        id="slow-ext",
        version="1.0.0",
        api_version=EXTENSION_API_VERSION,
        type="llm_provider",
        title="Slow",
    )
    provider = _SlowPayloadProvider()
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )
    manager._loaded = [
        LoadedExtension(manifest=manifest, source_dir=tmp_path / "slow-ext", provider=provider)
    ]

    first = manager.refresh_extension_tab("slow-ext", runtime=LLMRuntime(ProviderRegistry()))
    second = manager.refresh_extension_tab("slow-ext", runtime=LLMRuntime(ProviderRegistry()))

    assert first["job_id"] == second["job_id"]
    assert first["load_state"]["status"] == "refreshing"

    deadline = time.time() + 1.0
    payload = {}
    while time.time() < deadline:
        payload = manager.extension_tab_payload("slow-ext", runtime=LLMRuntime(ProviderRegistry()))
        if payload["load_state"]["status"] == "ready":
            break
        time.sleep(0.02)

    assert provider.calls == 1
    assert payload["load_state"]["status"] == "ready"


def test_bundled_extension_refreshes_existing_same_version_install(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    bundled = tmp_path / "bundled" / "sample-ext"
    bundled_backend = bundled / "backend"
    bundled_backend.mkdir(parents=True)
    manifest = {
        "id": "sample-ext",
        "version": "1.0.0",
        "api_version": EXTENSION_API_VERSION,
        "type": "ui_extension",
        "title": "Sample",
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    (bundled / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundled_backend / "provider.py").write_text("VALUE = 'fresh'\n", encoding="utf-8")

    installed = tmp_path / "installed" / "sample-ext" / "1.0.0"
    installed_backend = installed / "backend"
    installed_backend.mkdir(parents=True)
    (installed / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (installed_backend / "provider.py").write_text("VALUE = 'stale'\n", encoding="utf-8")

    repo = _Repo()
    state = [
        InstalledExtensionRecord(
            id="sample-ext",
            version="1.0.0",
            enabled=False,
            installed=True,
            source={"type": "bundled", "path": str(bundled)},
            title="Sample",
        )
    ]
    ExtensionsRepository(repo).save_records(state)
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    manager.ensure_builtin_installed("sample-ext")

    assert (installed_backend / "provider.py").read_text(encoding="utf-8") == "VALUE = 'fresh'\n"
    refreshed = ExtensionsRepository(repo).list_records()
    assert refreshed[0].enabled is False


def test_removed_bundled_extension_is_not_reinstalled(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=ExtensionRegistryClient(project_root=root),
        installed_dir=tmp_path / "installed",
        bundled_dir=root / "extensions" / "bundled",
        default_provider_id="ollama",
    )
    manager.bootstrap_runtime()
    assert any(item["id"] == "open-webui" for item in manager.installed_extensions())

    manager.remove("open-webui")
    manager.bootstrap_runtime()

    assert not any(item["id"] == "open-webui" for item in manager.installed_extensions())


def test_extension_install_rejects_unsafe_staged_extension_and_cleans_target(tmp_path: Path) -> None:
    class _Repo:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get_app_setting(self, key: str):
            return self.data.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.data[key] = value

    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "unsafe-ext",
                    "title": "Unsafe",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                }
            ]

    source = tmp_path / "source" / "unsafe-ext"
    backend = source / "backend"
    backend.mkdir(parents=True)
    manifest = {
        "id": "unsafe-ext",
        "version": "1.0.0",
        "api_version": EXTENSION_API_VERSION,
        "type": "ui_extension",
        "title": "Unsafe",
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    (source / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (backend / "provider.py").write_text(
        "import subprocess\n"
        "def create_provider(host_context, manifest):\n"
        "    subprocess.run(['cmd.exe', '/c', 'whoami'], check=False)\n"
        "    return object()\n",
        encoding="utf-8",
    )

    repo = _Repo()
    root = Path(__file__).resolve().parents[2]
    installed_dir = tmp_path / "installed"
    host = ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None)
    manager = ExtensionManager(
        project_root=root,
        host_context=host,
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=installed_dir,
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="Extension security audit blocked"):
        manager.install("unsafe-ext")

    assert not (installed_dir / "unsafe-ext" / "1.0.0").exists()
    assert ExtensionsRepository(repo).list_records() == []


def test_extension_zip_install_rejects_path_traversal_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            return None

    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "bad")
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(buf.getvalue()))

    root = Path(__file__).resolve().parents[2]
    repo = _Repo()
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="unsafe zip member path"):
        manager._download_zip_to_dir("https://example.invalid/ext.zip", tmp_path / "installed" / "unsafe" / "1")

    assert not (tmp_path / "evil.txt").exists()


def test_extension_zip_install_rejects_symlink_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            return None

    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    buf = BytesIO()
    info = zipfile.ZipInfo("sample-ext/assets/link.txt")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(info, "../secret.txt")
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(buf.getvalue()))

    root = Path(__file__).resolve().parents[2]
    repo = _Repo()
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="symlink"):
        manager._download_zip_to_dir("https://example.invalid/ext.zip", tmp_path / "installed" / "unsafe" / "1")


def test_extension_zip_install_rejects_uncompressed_size_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import llm_interactor.manager as manager_module

    class _Repo:
        def get_app_setting(self, key: str):
            return None

        def set_app_setting(self, key: str, value: str) -> None:
            return None

    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    monkeypatch.setattr(manager_module, "_MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES", 1024)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample-ext/payload.bin", b"0" * 2048)
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(buf.getvalue()))

    root = Path(__file__).resolve().parents[2]
    repo = _Repo()
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="expands beyond maximum allowed size"):
        manager._download_zip_to_dir("https://example.invalid/ext.zip", tmp_path / "installed" / "bomb" / "1")


def test_extension_asset_resolution_rejects_symlink_assets(tmp_path: Path) -> None:
    repo = _MemorySettingsRepo()
    installed_root = tmp_path / "installed"
    ext_root = installed_root / "sample-ext" / "1.0.0"
    assets = ext_root / "assets"
    assets.mkdir(parents=True)
    (assets / "good.txt").write_text("ok", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    link = assets / "link.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")
    ExtensionsRepository(repo).save_records(
        [
            InstalledExtensionRecord(
                id="sample-ext",
                version="1.0.0",
                enabled=True,
                installed=True,
                source={},
            )
        ]
    )
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=installed_root,
        bundled_dir=tmp_path / "bundled",
    )

    assert manager.resolve_asset_path("sample-ext", "assets/good.txt").name == "good.txt"
    with pytest.raises(FileNotFoundError):
        manager.resolve_asset_path("sample-ext", "assets/link.txt")


def test_registry_client_reads_local_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    client = ExtensionRegistryClient(project_root=root)
    rows = client.load()
    assert any(row["id"] == "ollama-provider" for row in rows)
    assert any(row["id"] == "open-webui" for row in rows)
    assert any(row["id"] == "codex-launcher" for row in rows)


def test_registry_entries_include_github_icon_url(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "icon": "icons/sample.svg",
                    "repository": "https://github.com/acme/sample-ext",
                    "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
                }
            ]

    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    row = manager.registry_entries()[0]

    assert row["icon"] == "icons/sample.svg"
    assert row["icon_url"] == "https://github.com/acme/sample-ext/raw/HEAD/icons/sample.svg"


def test_registry_client_loads_remote_registry_with_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "extensions": [
                    {
                        "id": "remote-ext",
                        "title": "Remote",
                        "repository": "https://github.com/acme/remote-ext",
                        "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
                    }
                ]
            }

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield json.dumps(self.json()).encode("utf-8")

    monkeypatch.setattr("requests.get", lambda url, timeout=30, stream=False: _Response())

    client = ExtensionRegistryClient("https://example.invalid/extensions.json", project_root=Path.cwd())
    result = client.load_with_diagnostics()

    assert result.diagnostics == []
    assert result.entries[0]["id"] == "remote-ext"


def test_registry_client_reports_bad_registry_shapes_and_missing_fields(tmp_path: Path) -> None:
    registry_path = tmp_path / "extensions.json"
    registry_path.write_text(
        json.dumps(
            {
                "extensions": [
                    "bad",
                    {"id": "missing-title", "repository": "https://github.com/acme/missing-title"},
                    {"id": "missing-source", "title": "Missing Source"},
                    {"id": "wrong-api", "title": "Wrong API", "repository": "https://github.com/acme/wrong-api", "compatibility": {"extension_api_version": "2"}},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = ExtensionRegistryClient(str(registry_path), project_root=tmp_path).load_with_diagnostics()
    codes = {item.code for item in result.diagnostics}

    assert result.entries == []
    assert "registry_entry_invalid" in codes
    assert "registry_entry_missing_title" in codes
    assert "registry_entry_missing_source" in codes
    assert "registry_entry_unsupported_api" in codes


def test_registry_client_uses_local_fallback_when_remote_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "extensions.json"
    registry_path.write_text(
        json.dumps({"extensions": [{"id": "fallback-ext", "title": "Fallback", "source_path": "extensions/bundled/open-webui"}]}),
        encoding="utf-8",
    )

    def _raise(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("requests.get", _raise)

    result = ExtensionRegistryClient(
        "https://example.invalid/extensions.json",
        project_root=Path.cwd(),
        fallback_url=str(registry_path),
    ).load_with_diagnostics()

    assert result.entries[0]["id"] == "fallback-ext"
    assert {item.code for item in result.diagnostics} == {"registry_load_failed_using_fallback"}


def test_extension_install_rejects_manifest_id_mismatch(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "expected-ext",
                    "title": "Expected",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(source, ext_id="actual-ext", version="1.0.0")
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="manifest id mismatch"):
        manager.install("expected-ext")

    assert not (tmp_path / "installed" / "expected-ext" / "1.0.0").exists()


def test_extension_install_rejects_manifest_version_mismatch(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(source, ext_id="sample-ext", version="2.0.0")
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="manifest version mismatch"):
        manager.install("sample-ext")


def test_extension_install_rejects_unsupported_registry_compatibility(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                    "compatibility": {"extension_api_version": "2", "app": "chironai"},
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(source, ext_id="sample-ext", version="1.0.0")
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    with pytest.raises(ValueError, match="unsupported extension_api_version"):
        manager.install("sample-ext")


def test_extension_details_and_install_resolve_latest_github_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "repository": "https://github.com/acme/sample-ext",
                    "repository_id": "repo-1",
                    "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
                }
            ]

    class _RepositoryClient:
        def __init__(self, zip_digest: str) -> None:
            self._digest = zip_digest

        def latest_release(self, repository: str) -> dict[str, object]:
            return {
                "version": "v1.0.0",
                "ref": "v1.0.0",
                "target_kind": "release",
                "archive_url": "https://github.com/acme/sample-ext/releases/download/v1.0.0/sample.zip",
                "digest": self._digest,
                "provenance_level": "github_release_asset",
                "is_latest": True,
            }

        def releases(self, repository: str) -> list[dict[str, object]]:
            return [self.latest_release(repository)]

        def tags(self, repository: str) -> list[dict[str, object]]:
            return [{"version": "v1.0.0", "ref": "v1.0.0", "target_kind": "tag"}]

        def readme(self, repository: str, *, ref: str | None = None) -> dict[str, object]:
            return {"repository": repository, "ref": ref or "", "markdown": "# Sample", "sanitized_html": "<pre># Sample</pre>"}

    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    buf = BytesIO()
    manifest = {
        "id": "sample-ext",
        "version": "1.0.0",
        "api_version": EXTENSION_API_VERSION,
        "type": "ui_extension",
        "title": "Sample",
        "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("sample-ext/chironai-extension.json", json.dumps(manifest))
        zf.writestr("sample-ext/backend/provider.py", "def create_provider(host_context, manifest):\n    return object()\n")
    zip_bytes = buf.getvalue()
    zip_digest = hashlib.sha256(zip_bytes).hexdigest()
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(zip_bytes))

    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        repository_client=_RepositoryClient(zip_digest),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    details = manager.extension_details("sample-ext")
    installed = manager.install("sample-ext")
    record = ExtensionsRepository(repo).list_records()[0]

    assert details["latest"]["ref"] == "v1.0.0"
    assert details["readme"]["markdown"] == "# Sample"
    assert installed["version"] == "v1.0.0"
    assert record.provenance["archive_url"] == "https://github.com/acme/sample-ext/releases/download/v1.0.0/sample.zip"
    assert record.provenance["digest"] == zip_digest


def test_extension_install_accepts_branch_refs_with_slashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "repository": "https://github.com/acme/sample-ext",
                }
            ]

    class _RepositoryClient:
        def releases(self, repository: str) -> list[dict[str, object]]:
            return []

    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    buf = BytesIO()
    manifest = {
        "id": "sample-ext",
        "version": "1.0.0",
        "api_version": EXTENSION_API_VERSION,
        "type": "ui_extension",
        "title": "Sample",
        "compatibility": {"extension_api_version": EXTENSION_API_VERSION, "app": "chironai"},
        "backend": {"entrypoint": "backend.provider:create_provider"},
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("sample-ext/chironai-extension.json", json.dumps(manifest))
        zf.writestr("sample-ext/backend/provider.py", "def create_provider(host_context, manifest):\n    return object()\n")
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(buf.getvalue()))

    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        repository_client=_RepositoryClient(),
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    result = manager.install("sample-ext", target={"ref": "feature/github-registry", "target_kind": "branch"})
    record = ExtensionsRepository(repo).list_records()[0]

    assert result["selected_ref"] == "feature/github-registry"
    assert "/" not in result["version"]
    assert record.provenance["selected_ref"] == "feature/github-registry"
    assert record.provenance["storage_version"] == result["version"]
    assert (tmp_path / "installed" / "sample-ext" / result["version"]).is_dir()


def test_extension_install_preserves_previous_safe_version_when_update_scan_fails(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(source, ext_id="sample-ext", version="1.0.0")
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    manager.install("sample-ext")
    installed_provider = tmp_path / "installed" / "sample-ext" / "1.0.0" / "backend" / "provider.py"
    assert "subprocess" not in installed_provider.read_text(encoding="utf-8")

    _write_minimal_extension(source, ext_id="sample-ext", version="1.0.0", unsafe=True)

    with pytest.raises(ValueError, match="Extension security audit blocked"):
        manager.install("sample-ext")

    assert "subprocess" not in installed_provider.read_text(encoding="utf-8")
    record = ExtensionsRepository(repo).list_records()[0]
    assert record.provenance["selected_ref"] == "1.0.0"
    assert record.security_scan["status"] == "passed"


def test_extension_install_rejects_blocklisted_ref(tmp_path: Path) -> None:
    class _Registry:
        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "source_path": str(source),
                    "latest_version": "1.0.0",
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(source, ext_id="sample-ext", version="1.0.0")
    blocklist = tmp_path / "blocklist.json"
    blocklist.write_text(
        json.dumps({"blocked": [{"extension_id": "sample-ext", "ref": "1.0.0", "reason": "compromised"}]}),
        encoding="utf-8",
    )
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=_Registry(),  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
        blocklist_policy=ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path),
    )

    with pytest.raises(ValueError, match="blocked by emergency blocklist"):
        manager.install("sample-ext")

    assert ExtensionsRepository(repo).list_records() == []


def test_extension_update_requires_consent_for_high_risk_capability_expansion(tmp_path: Path) -> None:
    class _Registry:
        def __init__(self) -> None:
            self.version = "1.0.0"

        def load(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "sample-ext",
                    "title": "Sample",
                    "source_path": str(source),
                    "latest_version": self.version,
                }
            ]

    source = tmp_path / "source"
    _write_minimal_extension(
        source,
        ext_id="sample-ext",
        version="1.0.0",
        capabilities={"chat": True},
    )
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    registry = _Registry()
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        registry_client=registry,  # type: ignore[arg-type]
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
    )

    manager.install("sample-ext")

    registry.version = "2.0.0"
    shutil.rmtree(source)
    _write_minimal_extension(
        source,
        ext_id="sample-ext",
        version="2.0.0",
        capabilities={"chat": True, "service_actions": True},
    )

    with pytest.raises(ValueError, match="high-risk capabilities requiring consent: service_actions"):
        manager.install("sample-ext")

    result = manager.install("sample-ext", target={"allow_capability_expansion": True})
    record = ExtensionsRepository(repo).list_records()[0]

    assert result["version"] == "2.0.0"
    assert result["capability_expansion"][0]["id"] == "service_actions"
    assert record.capabilities["service_actions"] is True


def test_blocklisted_installed_extension_is_disabled_on_bootstrap(tmp_path: Path) -> None:
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    installed = tmp_path / "installed" / "sample-ext" / "1.0.0"
    _write_minimal_extension(installed, ext_id="sample-ext", version="1.0.0")
    ExtensionsRepository(repo).save_records(
        [
            InstalledExtensionRecord(
                id="sample-ext",
                version="1.0.0",
                enabled=True,
                installed=True,
                source={"type": "test"},
                title="Sample",
                provenance={"selected_ref": "1.0.0"},
            )
        ]
    )
    blocklist = tmp_path / "blocklist.json"
    blocklist.write_text(
        json.dumps({"blocked": [{"extension_id": "sample-ext", "reason": "emergency disable"}]}),
        encoding="utf-8",
    )
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
        use_sandbox=False,
        blocklist_policy=ExtensionBlocklistPolicy(str(blocklist), project_root=tmp_path),
    )

    manager.bootstrap_runtime()

    record = ExtensionsRepository(repo).list_records()[0]
    row = manager.installed_extensions()[0]
    assert record.enabled is False
    assert record.security_scan["scanner"] == "chironai_blocklist"
    assert row["status"] == "blocked"
    assert row["blocklist"]["matched"] is True
    with pytest.raises(ValueError, match="blocked by emergency blocklist"):
        manager.enable("sample-ext")


def test_extension_security_failure_disables_installed_extension(tmp_path: Path) -> None:
    repo = _MemorySettingsRepo()
    root = Path(__file__).resolve().parents[2]
    installed = tmp_path / "installed" / "sample-ext" / "1.0.0"
    _write_minimal_extension(installed, ext_id="sample-ext", version="1.0.0", unsafe=True)
    ExtensionsRepository(repo).save_records(
        [
            InstalledExtensionRecord(
                id="sample-ext",
                version="1.0.0",
                enabled=True,
                installed=True,
                source={"type": "test"},
                title="Sample",
            )
        ]
    )
    manager = ExtensionManager(
        project_root=root,
        host_context=ProviderHostContext(project_root=root, get_settings_repository=lambda: repo, chat_client=None),
        settings_repo=repo,
        installed_dir=tmp_path / "installed",
        bundled_dir=tmp_path / "bundled",
        use_sandbox=False,
    )

    manager.bootstrap_runtime()

    record = ExtensionsRepository(repo).list_records()[0]
    assert record.enabled is False
    assert record.security_scan["status"] == "blocked"
    assert record.restart_scope == "provider_registry"
    assert manager.installed_extensions()[0]["status"] == "blocked"
