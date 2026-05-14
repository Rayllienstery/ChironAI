"""Tests for rag_service runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rag_service.runtime import RagRuntime, RagRuntimeConfig, ollama_ping, qdrant_port_from_url


class _DockerManager:
    def __init__(self) -> None:
        self.ensure_spec = None
        self.stopped = ""

    def status(self) -> dict[str, object]:
        return {"ok": True, "cli_available": True, "engine_ready": True}

    def container_running(self, name: str) -> bool:
        return False

    def wait_engine_tuple(self, **kwargs: object) -> tuple[bool, str]:
        return True, "docker engine ready"

    def ensure_container(self, spec) -> dict[str, object]:
        self.ensure_spec = spec
        return {"ok": True, "container": spec.name, "message": "created"}

    def stop_container(self, name: str) -> dict[str, object]:
        self.stopped = name
        return {"ok": True, "container": name, "message": "stopped"}


def test_qdrant_port_from_url() -> None:
    assert qdrant_port_from_url("http://localhost:6333") == 6333
    assert qdrant_port_from_url("http://example.com:7777") == 7777


def test_ollama_ping_ok() -> None:
    fake_resp = MagicMock()
    fake_resp.ok = True
    fake_resp.status_code = 200
    with patch("rag_service.runtime.requests.get", return_value=fake_resp):
        out = ollama_ping("http://localhost:11434", timeout=1.0)
    assert out["ok"] is True
    assert out["status_code"] == 200


def test_runtime_health_shape() -> None:
    cfg = RagRuntimeConfig.from_env()
    rt = RagRuntime(cfg)

    fake_ollama = {"ok": True, "url": cfg.ollama_base_url, "status_code": 200}

    fake_q = MagicMock()
    fake_q.ok = True
    fake_q.status_code = 200

    def _fake_get(url: str, **kwargs: object) -> MagicMock:
        assert kwargs is not None
        return fake_q

    with (
        patch("rag_service.runtime.ollama_ping", return_value=fake_ollama),
        patch("rag_service.runtime._docker_manager", return_value=_DockerManager()),
        patch("rag_service.runtime.requests.get", side_effect=_fake_get),
    ):
        st = rt.health()

    assert st["ollama"]["running"] is True
    assert "docker" in st
    assert st["qdrant"]["running"] is True


def test_runtime_start_dependencies_shape() -> None:
    rt = RagRuntime(RagRuntimeConfig.from_env())
    with (
        patch.object(rt, "start_qdrant", return_value=(True, "ok")),
        patch.object(rt, "health", return_value={"ollama": {"running": True}, "qdrant": {"running": True}}),
    ):
        out = rt.start_dependencies(["ollama", "qdrant"])
    assert out["ollama"][0] is False
    assert "ChironAI" in out["ollama"][1] or "Ollama tab" in out["ollama"][1]
    assert out["qdrant"] == (True, "ok")
    assert "health" in out


def test_runtime_qdrant_uses_docker_manager_spec() -> None:
    cfg = RagRuntimeConfig.from_env()
    rt = RagRuntime(cfg)
    docker = _DockerManager()

    with (
        patch("rag_service.runtime._docker_manager", return_value=docker),
        patch("rag_service.runtime.wait_for_http_json", return_value=(True, None)),
    ):
        started = rt.start_qdrant()
        stopped = rt.stop_qdrant()

    assert started == (True, "created")
    assert stopped == (True, "stopped")
    assert docker.ensure_spec.name == cfg.qdrant_container_name
    assert docker.ensure_spec.image == cfg.qdrant_image
    assert docker.ensure_spec.ports == [
        f"{cfg.qdrant_host_http_port}:6333",
        f"{cfg.qdrant_host_grpc_port}:6334",
    ]
    assert docker.ensure_spec.volumes == ["qdrant_storage:/qdrant/storage"]
    assert docker.stopped == cfg.qdrant_container_name
