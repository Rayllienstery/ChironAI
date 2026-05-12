from __future__ import annotations

import json
from pathlib import Path

from llm_interactor import ProviderHostContext
from llm_interactor.discovery import discover_extensions


class _Repo:
    def get_app_setting(self, key: str):
        return None

    def set_app_setting(self, key: str, value: str) -> None:
        return None


def _write_extension(root: Path, *, extension_id: str, provider_py: str) -> Path:
    ext = root / extension_id
    backend = ext / "backend"
    backend.mkdir(parents=True)
    (backend / "provider.py").write_text(provider_py, encoding="utf-8")
    (ext / "chironai-extension.json").write_text(
        json.dumps(
            {
                "id": extension_id,
                "version": "1.0.0",
                "api_version": "1",
                "type": "llm_provider",
                "title": extension_id,
                "backend": {"entrypoint": "backend.provider:create_provider"},
                "capabilities": {"tab_ui": True},
            }
        ),
        encoding="utf-8",
    )
    return ext


def _host(tmp_path: Path) -> ProviderHostContext:
    return ProviderHostContext(
        project_root=tmp_path,
        get_settings_repository=lambda: _Repo(),
        docker_runtime=object(),
    )


def test_extension_using_docker_runtime_contract_loads(tmp_path: Path) -> None:
    ext = _write_extension(
        tmp_path,
        extension_id="valid-docker-extension",
        provider_py="""
class Provider:
    def __init__(self, host_context, manifest):
        self._docker = host_context.docker_runtime

    def describe(self):
        return None

def create_provider(host_context, manifest):
    from docker_manager import DockerContainerSpec
    DockerContainerSpec(name="svc", image="example/service:latest")
    return Provider(host_context, manifest)
""",
    )

    report = discover_extensions([ext], host_context=_host(tmp_path))

    assert [item.manifest.id for item in report.loaded] == ["valid-docker-extension"]
    assert report.failed == []


def test_extension_subprocess_docker_access_is_rejected(tmp_path: Path) -> None:
    ext = _write_extension(
        tmp_path,
        extension_id="bad-subprocess-extension",
        provider_py="""
import subprocess

def create_provider(host_context, manifest):
    subprocess.run(["docker", "ps"], check=False)
    return object()
""",
    )

    report = discover_extensions([ext], host_context=_host(tmp_path))

    assert report.loaded == []
    assert report.failed[0].extension_id == "bad-subprocess-extension"
    assert "host_context.docker_runtime" in report.failed[0].error


def test_extension_coreui_docker_route_access_is_rejected(tmp_path: Path) -> None:
    ext = _write_extension(
        tmp_path,
        extension_id="bad-route-extension",
        provider_py="""
def create_provider(host_context, manifest):
    url = "/api/webui/docker/containers"
    return {"url": url}
""",
    )

    report = discover_extensions([ext], host_context=_host(tmp_path))

    assert report.loaded == []
    assert report.failed[0].extension_id == "bad-route-extension"
    assert "host_context.docker_runtime" in report.failed[0].error
