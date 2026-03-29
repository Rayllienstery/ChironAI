"""Ollama upstream URL helpers."""

from llm_proxy.ollama_upstream import ollama_api_base_from_chat_url


def test_ollama_api_base_from_chat_url() -> None:
    assert ollama_api_base_from_chat_url("http://127.0.0.1:11434/api/chat") == "http://127.0.0.1:11434"
    assert ollama_api_base_from_chat_url("http://host:8080/api/chat/") == "http://host:8080"
