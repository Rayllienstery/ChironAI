"""Tests for get_ollama_base_url (WebUI /api/tags must match chat client host:port)."""

from __future__ import annotations

import pytest


def test_get_ollama_base_url_from_chat_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_CHAT_URL", "http://custom-host:11434/api/chat")
    assert cfg.get_ollama_base_url() == "http://custom-host:11434"


def test_get_ollama_base_url_explicit_strips_api_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.5:11434/api/chat")
    monkeypatch.delenv("OLLAMA_CHAT_URL", raising=False)
    assert cfg.get_ollama_base_url() == "http://192.168.1.5:11434"


def test_get_ollama_base_url_uses_yaml_chat_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """When env unset, base is derived from bundled models.yaml chat_url host:port."""
    import config as cfg

    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_CHAT_URL", raising=False)
    base = cfg.get_ollama_base_url()
    assert base.startswith("http://")
    assert ":11434" in base


def test_get_ollama_rerank_model_does_not_use_retrieval_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg
    import config.loader as loader

    monkeypatch.setattr(loader, "_rsc", None)
    monkeypatch.delenv("OLLAMA_RERANK_MODEL", raising=False)
    monkeypatch.setitem(loader.OLLAMA_CONFIG, "rerank_model", "")
    monkeypatch.setitem(loader.OLLAMA_CONFIG, "rerank_model_last_resort", "fallback-rerank")
    monkeypatch.setitem(loader.RETRIEVAL_CONFIG, "rerank_model", "wrong-devstral-rerank")

    assert cfg.get_ollama_rerank_model() == "fallback-rerank"
