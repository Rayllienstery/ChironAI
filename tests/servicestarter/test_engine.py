"""Tests for ServiceStarter.status() with mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from servicestarter.config import ServiceStarterConfig
from servicestarter.engine import ServiceStarter


def test_status_shape() -> None:
    cfg = ServiceStarterConfig.from_env()
    ss = ServiceStarter(cfg)

    fake_ollama = {"ok": True, "url": cfg.ollama_base_url, "status_code": 200}

    fake_q = MagicMock()
    fake_q.ok = True
    fake_q.status_code = 200
    fake_q.json.return_value = {"result": {"collections": []}}

    fake_open = MagicMock()
    fake_open.ok = True
    fake_open.status_code = 200

    def _fake_get(url: str, **kwargs: object) -> MagicMock:
        if "6333" in url or "/collections" in url:
            return fake_q
        return fake_open

    with (
        patch("servicestarter.engine.ollama_ops.ollama_ping", return_value=fake_ollama),
        patch("servicestarter.engine.docker_ops.docker_version_available", return_value=True),
        patch("servicestarter.engine.docker_ops.docker_engine_ready", return_value=True),
        patch("servicestarter.engine.docker_ops.container_is_running", return_value=False),
        patch("servicestarter.engine.requests.get", side_effect=_fake_get),
    ):
        st = ss.status()

    assert st["ollama"]["running"] is True
    assert st["ollama"]["port"] == 11343
    assert st["docker"]["engine_available"] is True
    assert st["qdrant"]["running"] is True
    assert "open_webui" not in st
