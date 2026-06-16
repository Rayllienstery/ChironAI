"""Documented config precedence: env overrides YAML when both are set."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_rag_service_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import config.loader as loader

    monkeypatch.setattr(loader, "_rsc", None)


def test_get_rag_int_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.delenv("RAG_CONTEXT_CHUNK_CHARS", raising=False)
    monkeypatch.setitem(cfg.RAG_CONFIG, "context_chunk_chars", 1000)
    assert cfg.get_rag_int("context_chunk_chars", 500) == 1000

    monkeypatch.setenv("RAG_CONTEXT_CHUNK_CHARS", "2400")
    assert cfg.get_rag_int("context_chunk_chars", 500) == 2400


def test_get_retrieval_int_top_k_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.delenv("RAG_TOP_K", raising=False)
    monkeypatch.setitem(cfg.RETRIEVAL_CONFIG, "top_k", 8)
    assert cfg.get_retrieval_int("top_k", 4) == 8

    monkeypatch.setenv("RAG_TOP_K", "16")
    assert cfg.get_retrieval_int("top_k", 4) == 16


def test_get_ollama_chat_model_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.delenv("OLLAMA_CHAT_MODEL", raising=False)
    monkeypatch.setitem(cfg.OLLAMA_CONFIG, "chat_model", "yaml-model")
    assert cfg.get_ollama_chat_model() == "yaml-model"

    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "env-model")
    assert cfg.get_ollama_chat_model() == "env-model"


def test_get_qdrant_url_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import config as cfg

    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setitem(cfg.QDRANT_CONFIG, "url", "http://yaml:6333")
    assert cfg.get_qdrant_url() == "http://yaml:6333"

    monkeypatch.setenv("QDRANT_URL", "http://env:6333")
    assert cfg.get_qdrant_url() == "http://env:6333"
