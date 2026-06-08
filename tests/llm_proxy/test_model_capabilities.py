from __future__ import annotations

from typing import Any

import requests


def test_get_cached_ollama_capabilities_reads_api_tags(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "models": [
                    {
                        "name": "deepseek-v4-pro:cloud",
                        "capabilities": ["completion", "tools", "thinking"],
                    },
                    {
                        "name": "minimax-m3:cloud",
                        "capabilities": ["completion", "tools", "vision"],
                    },
                ]
            }

    called: list[str] = []

    def fake_get(url: str, timeout: float):
        called.append(url)
        assert timeout == 2.5
        return Response()

    monkeypatch.setattr(mc.requests, "get", fake_get)

    deepseek_caps = mc.get_cached_ollama_capabilities(
        "deepseek-v4-pro:cloud",
        "http://localhost:11434/api/chat",
    )
    assert deepseek_caps == frozenset({"completion", "tools", "thinking"})
    assert mc.caps_supports_vision(deepseek_caps) is False
    assert mc.find_cached_ollama_vision_model(
        "http://localhost:11434/api/chat",
        preferred_models=("minimax-m3:cloud",),
    ) == "minimax-m3:cloud"
    assert called == ["http://localhost:11434/api/tags"]


def test_get_cached_ollama_capabilities_accepts_model_key_and_api_subpath(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"models": [{"model": "vision-model", "capabilities": ["IMAGE", "tools"]}]}

    called: list[str] = []

    def fake_get(url: str, timeout: float):
        called.append(url)
        return Response()

    monkeypatch.setattr(mc.requests, "get", fake_get)

    caps = mc.get_cached_ollama_capabilities("vision-model", "http://ollama.local/root/api/chat")

    assert caps == frozenset({"image", "tools"})
    assert mc.caps_supports_vision(caps) is True
    assert called == ["http://ollama.local/root/api/tags"]


def test_get_cached_ollama_capabilities_returns_none_for_bad_inputs_and_missing_model(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "models": [
                    "bad-row",
                    {"name": "", "capabilities": ["vision"]},
                    {"name": "no-caps", "capabilities": "vision"},
                    {"name": "text-only", "capabilities": ["completion"]},
                ]
            }

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: Response())

    assert mc.get_cached_ollama_capabilities("", "http://localhost:11434/api/chat") is None
    assert mc.get_cached_ollama_capabilities("x", "not-a-url") is None
    assert mc.get_cached_ollama_capabilities("missing", "http://localhost:11434/api/chat") is None
    assert mc.find_cached_ollama_vision_model("http://localhost:11434/api/chat") is None


def test_cached_ollama_tags_handles_http_and_json_failures(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    def fail_get(*_a, **_k):
        raise requests.RequestException("offline")

    monkeypatch.setattr(mc.requests, "get", fail_get)
    assert mc.get_cached_ollama_capabilities("x", "http://localhost:11434/api/chat") is None

    mc._cached_ollama_tags.cache_clear()

    class BadJsonResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            raise ValueError("bad json")

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: BadJsonResponse())
    assert mc.find_cached_ollama_vision_model("http://localhost:11434/api/chat") is None


def test_find_cached_ollama_vision_model_uses_preference_then_first_vision(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "models": [
                    {"name": "first-vision", "capabilities": ["vision"]},
                    {"name": "preferred-vision", "capabilities": ["completion", "images"]},
                ]
            }

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: Response())

    assert (
        mc.find_cached_ollama_vision_model(
            "http://localhost:11434/api/chat",
            preferred_models=("text-only", "preferred-vision"),
        )
        == "preferred-vision"
    )
    assert mc.find_cached_ollama_vision_model("http://localhost:11434/api/chat") == "first-vision"


def test_ollama_tags_url_handles_empty_api_subpaths_and_base_urls() -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    assert mc._ollama_tags_url_from_chat_url("") is None
    assert mc._ollama_tags_url_from_chat_url("localhost:11434/api/chat") is None
    assert mc._ollama_tags_url_from_chat_url("http://localhost:11434/api/generate") == (
        "http://localhost:11434/api/tags"
    )
    assert mc._ollama_tags_url_from_chat_url("http://localhost:11434") == "http://localhost:11434/api/tags"


def test_cached_ollama_tags_ignores_non_list_models_and_type_errors(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()

    class NonListModelsResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"models": {"name": "not-a-list"}}

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: NonListModelsResponse())
    assert mc.get_cached_ollama_capabilities("x", "http://localhost:11434/api/chat") is None

    mc._cached_ollama_tags.cache_clear()

    class TypeErrorResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            raise TypeError("bad json type")

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: TypeErrorResponse())
    assert mc.get_cached_ollama_capabilities("x", "http://localhost:11434/api/chat") is None


def test_find_cached_ollama_vision_model_bad_url_and_no_tags(monkeypatch) -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    mc._cached_ollama_tags.cache_clear()
    assert mc.find_cached_ollama_vision_model("bad-url") is None

    class EmptyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"models": []}

    monkeypatch.setattr(mc.requests, "get", lambda *_a, **_k: EmptyResponse())
    assert mc.find_cached_ollama_vision_model("http://localhost:11434/api/chat") is None


def test_misc_capability_predicates() -> None:
    from llm_proxy.wire_format import model_capabilities as mc

    assert mc.caps_supports_tools(frozenset({"tools"})) is True
    assert mc.caps_supports_thinking(frozenset({"think"})) is True
    assert mc.ollama_native_think_troublesome_model("Qwen3:latest") is True
    assert mc.ollama_native_think_troublesome_model(None) is False
    assert mc.chat_error_suggests_no_tools(RuntimeError("model does not support tools")) is True
    assert mc.chat_error_suggests_no_tools(RuntimeError("other")) is False
    assert mc.chat_error_suggests_no_think(RuntimeError("unsupported think parameter")) is True
    assert mc.chat_error_suggests_no_think(RuntimeError("think is not supported here")) is True
    assert mc.chat_error_suggests_no_think(RuntimeError("other")) is False
