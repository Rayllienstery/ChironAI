"""Tests for ServiceStarter DockerManager adapters."""

from __future__ import annotations

from unittest.mock import patch

from servicestarter.config import ServiceStarterConfig
from servicestarter.docker_ops import (
    container_is_running,
    container_name_matches_running,
    docker_start_container,
    ensure_qdrant_container,
    qdrant_port_from_url,
)


class _Manager:
    def __init__(self) -> None:
        self.ensure_spec = None

    def containers(self) -> dict[str, object]:
        return {"ok": True, "containers": [{"name": "sample-service", "running": True}]}

    def container_running(self, name: str) -> bool:
        return name == "sample-service"

    def start_container(self, name: str) -> dict[str, object]:
        return {"ok": True, "container": name, "message": "started"}

    def ensure_container(self, spec) -> dict[str, object]:
        self.ensure_spec = spec
        return {"ok": True, "container": spec.name, "message": "created"}


def test_qdrant_port_from_url() -> None:
    assert qdrant_port_from_url("http://localhost:6333") == 6333
    assert qdrant_port_from_url("http://example.com:7777") == 7777


def test_container_name_matches_running_true() -> None:
    with patch("servicestarter.docker_ops._manager", return_value=_Manager()):
        assert container_name_matches_running("sample-service") is True


def test_container_name_matches_running_false() -> None:
    manager = _Manager()
    manager.containers = lambda: {"ok": True, "containers": []}  # type: ignore[method-assign]
    with patch("servicestarter.docker_ops._manager", return_value=manager):
        assert container_name_matches_running("qdrant") is False


def test_container_is_running_true() -> None:
    with patch("servicestarter.docker_ops._manager", return_value=_Manager()):
        assert container_is_running("sample-service") is True


def test_container_is_running_false() -> None:
    with patch("servicestarter.docker_ops._manager", return_value=_Manager()):
        assert container_is_running("other-service") is False


def test_docker_start_delegates_to_manager() -> None:
    with patch("servicestarter.docker_ops._manager", return_value=_Manager()):
        ok, msg = docker_start_container("sample-service")
    assert ok is True
    assert msg == "started"


def test_ensure_qdrant_container_builds_contract_spec() -> None:
    cfg = ServiceStarterConfig.from_env()
    manager = _Manager()

    with patch("servicestarter.docker_ops._manager", return_value=manager):
        ok, msg = ensure_qdrant_container(cfg)

    assert ok is True
    assert msg == "created"
    assert manager.ensure_spec.name == cfg.qdrant_container_name
    assert manager.ensure_spec.image == cfg.qdrant_image
    assert manager.ensure_spec.ports == [
        f"{cfg.qdrant_host_http_port}:6333",
        f"{cfg.qdrant_host_grpc_port}:6334",
    ]
    assert manager.ensure_spec.volumes == ["qdrant_storage:/qdrant/storage"]
