"""Tests for rag_service runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rag_service.runtime import RagRuntime, RagRuntimeConfig, ollama_ping, qdrant_port_from_url


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
        patch("rag_service.runtime.docker_version_available", return_value=True),
        patch("rag_service.runtime.docker_engine_ready", return_value=True),
        patch("rag_service.runtime.container_is_running", return_value=False),
        patch("rag_service.runtime.requests.get", side_effect=_fake_get),
    ):
        st = rt.health()

    assert st["ollama"]["running"] is True
    assert "docker" in st
    assert st["qdrant"]["running"] is True


def test_runtime_start_dependencies_shape() -> None:
    rt = RagRuntime(RagRuntimeConfig.from_env())
    with (
        patch.object(rt, "start_ollama", return_value=(True, "ok")),
        patch.object(rt, "start_qdrant", return_value=(True, "ok")),
        patch.object(rt, "health", return_value={"ollama": {"running": True}, "qdrant": {"running": True}}),
    ):
        out = rt.start_dependencies(["ollama", "qdrant"])
    assert out["ollama"] == (True, "ok")
    assert out["qdrant"] == (True, "ok")
    assert "health" in out
