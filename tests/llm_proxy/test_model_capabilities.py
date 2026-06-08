from __future__ import annotations

from typing import Any


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
