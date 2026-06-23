"""Unit tests for llm_proxy.config."""

from llm_proxy.config import AUTOCOMPLETE_MODEL_ID, LlmProxyRuntimeConfig


def test_llm_proxy_runtime_config_defaults() -> None:
    c = LlmProxyRuntimeConfig()
    assert c.autocomplete_model_logical_id == AUTOCOMPLETE_MODEL_ID


def test_autocomplete_model_id_constant() -> None:
    assert AUTOCOMPLETE_MODEL_ID == "ChironAI-Autocomplete"


def test_llm_proxy_runtime_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROXY_AUTOCOMPLETE_MODEL_ID", "my-ac-id")
    rt = LlmProxyRuntimeConfig.from_env()
    assert rt.autocomplete_model_logical_id == "my-ac-id"
