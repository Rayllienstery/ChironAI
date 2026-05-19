from __future__ import annotations

import json
import zipfile
from io import BytesIO
import sys
from pathlib import Path

import pytest

from llm_interactor import (
    EXTENSION_API_VERSION,
    ExtensionManager,
    ExtensionRegistryClient,
    ExtensionsRepository,
    InstalledExtensionRecord,
    LLMRequest,
    LLMResponse,
    LLMRuntime,
    LLMStreamEvent,
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
    assert any(desc.id == "ollama" and desc.title == "Ollama" for desc in descriptors)
    catalog = manager.provider_catalog(runtime=bootstrap.runtime, capability="chat")
    assert any(row["provider_id"] == "ollama" and row["title"] == "Ollama" for row in catalog["providers"])
    tabs = manager.extension_tabs(runtime=bootstrap.runtime)
    assert any(tab["id"] == "open-webui" and "status" in tab for tab in tabs)
    assert any(tab["id"] == "ollama" and tab.get("frame", {}).get("id") == "ollama-runtime-frame" for tab in tabs)
    assert any(tab["id"] == "codex" and tab.get("extension_id") == "codex-launcher" for tab in tabs)
    assert any(tab["id"] == "open-webui" and tab.get("frame") == {} for tab in tabs)
    assert any(tab["id"] == "ollama" and tab.get("icon_url", "").endswith("/icons/ollama-light.svg") for tab in tabs)


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
            self.content = content

        def raise_for_status(self) -> None:
            return None

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "bad")
    monkeypatch.setattr("requests.get", lambda url, timeout: _Response(buf.getvalue()))

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


def test_registry_client_reads_local_registry() -> None:
    root = Path(__file__).resolve().parents[2]
    client = ExtensionRegistryClient(project_root=root)
    rows = client.load()
    assert any(row["id"] == "ollama-provider" for row in rows)
    assert any(row["id"] == "open-webui" for row in rows)
    assert any(row["id"] == "codex-launcher" for row in rows)
