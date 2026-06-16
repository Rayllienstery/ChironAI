"""Characterization tests for config package split (loader + env)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_rag_service_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import config.loader as loader

    monkeypatch.setattr(loader, "_rsc", None)


def test_config_loader_exposes_yaml_sections() -> None:
    import config

    assert isinstance(config.RAG_CONFIG, dict)
    assert isinstance(config.SERVER_CONFIG, dict)
    assert isinstance(config.OLLAMA_CONFIG, dict)


def test_config_env_getters_importable() -> None:
    import config

    assert callable(config.get_qdrant_url)
    assert callable(config.get_server_port)
    assert callable(config.get_ollama_chat_model)


def test_loader_and_env_modules_distinct() -> None:
    import config.env as env
    import config.loader as loader

    assert hasattr(loader, "_load_yaml")
    assert hasattr(env, "get_rag_int")
    assert not hasattr(loader, "get_rag_int")
