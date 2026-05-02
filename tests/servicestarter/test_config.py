"""Tests for ServiceStarterConfig.from_env defaults and overrides."""

from __future__ import annotations


import pytest

from servicestarter.config import ServiceStarterConfig


@pytest.fixture
def clean_ollama_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "OLLAMA_PORT",
        "OLLAMA_LISTEN_HOST",
        "OLLAMA_BASE_URL",
        "OLLAMA_HOST_VALUE",
        "QDRANT_URL",
    ):
        monkeypatch.delenv(k, raising=False)


@pytest.mark.usefixtures("clean_ollama_env")
def test_default_ollama_port_11343() -> None:
    cfg = ServiceStarterConfig.from_env()
    assert ":11343" in cfg.ollama_base_url or cfg.ollama_base_url.endswith("11343")
    assert "11343" in cfg.ollama_listen


def test_ollama_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9999")
    cfg = ServiceStarterConfig.from_env()
    assert cfg.ollama_base_url == "http://127.0.0.1:9999"
