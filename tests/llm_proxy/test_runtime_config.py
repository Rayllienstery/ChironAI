"""Unit tests for llm_proxy.config."""

from __future__ import annotations

from llm_proxy.config import LlmProxyRuntimeConfig, RAG_MODEL_ID


def test_runtime_config_defaults() -> None:
    c = LlmProxyRuntimeConfig()
    assert c.rag_model_logical_id == RAG_MODEL_ID
    assert c.recent_success_ttl_s == 45.0
    assert c.recent_noop_ttl_s == 120.0


def test_rag_model_id_constant() -> None:
    assert RAG_MODEL_ID == "rag-ollama"
