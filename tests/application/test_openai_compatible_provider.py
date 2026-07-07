from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.openai_compatible_provider import (
    OpenAICompatibleProvider,
    _extract_assistant_text,
    _headers_for_record,
    _ollama_body_to_openai,
    _openai_chat_url,
    _openai_models_url,
)
from core.contracts.llm_runtime import LLMRequest


def _record(**overrides: object) -> dict[str, object]:
    base = {
        "id": "test-gateway",
        "display_name": "Test Gateway",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-secret",
        "manual_models": ["manual-model"],
    }
    base.update(overrides)
    return base


def test_openai_url_helpers() -> None:
    assert _openai_chat_url("https://api.example.com") == "https://api.example.com/v1/chat/completions"
    assert _openai_chat_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
    assert _openai_models_url("https://api.example.com") == "https://api.example.com/v1/models"
    assert _openai_models_url("https://api.example.com/v1/") == "https://api.example.com/v1/models"


def test_headers_for_record_includes_auth_and_custom_headers() -> None:
    headers = _headers_for_record(
        {
            "api_key": "sk-test",
            "organization": "org-1",
            "default_headers": {"X-Custom": "yes"},
        },
    )
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["OpenAI-Organization"] == "org-1"
    assert headers["X-Custom"] == "yes"


def test_ollama_body_to_openai_maps_options_and_tools() -> None:
    payload = _ollama_body_to_openai(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "options": {"temperature": 0.2, "top_p": 0.9},
            "max_tokens": 128,
            "tools": [{"type": "function", "function": {"name": "fn"}}],
            "tool_choice": "auto",
        },
    )
    assert payload["model"] == "gpt-4o-mini"
    assert payload["temperature"] == 0.2
    assert payload["top_p"] == 0.9
    assert payload["max_tokens"] == 128
    assert payload["tools"]
    assert payload["tool_choice"] == "auto"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"message": {"content": "direct"}}, "direct"),
        ({"choices": [{"message": {"content": "choice"}}]}, "choice"),
        ({"choices": [{"text": "legacy"}]}, "legacy"),
        ({"response": "ollama"}, "ollama"),
        ({}, ""),
    ],
)
def test_extract_assistant_text(raw: dict[str, object], expected: str) -> None:
    assert _extract_assistant_text(raw) == expected


def test_describe_marks_custom_openai_source() -> None:
    provider = OpenAICompatibleProvider(_record())
    desc = provider.describe()
    assert desc.id == "test-gateway"
    assert desc.metadata["source"] == "custom_openai"


def test_list_models_merges_manual_models_when_upstream_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(_record())
    monkeypatch.setattr(provider, "_request", MagicMock(side_effect=RuntimeError("offline")))

    models = provider.list_models()

    assert [model.id for model in models] == ["manual-model"]


def test_test_connection_reports_model_count(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(_record())
    monkeypatch.setattr(
        provider,
        "health_check",
        MagicMock(return_value=MagicMock(ok=True, status="ok", message="")),
    )
    monkeypatch.setattr(
        provider,
        "list_models",
        MagicMock(
            return_value=[
                MagicMock(id="gpt-4o-mini", label="gpt-4o-mini"),
            ]
        ),
    )

    result = provider.test_connection()

    assert result["ok"] is True
    assert result["model_count"] == 1
    assert result["models"][0]["id"] == "gpt-4o-mini"


def test_invoke_chat_returns_extracted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(_record())
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    monkeypatch.setattr(provider, "_request", MagicMock(return_value=response))

    result = provider.invoke(
        LLMRequest(
            provider_id="test-gateway",
            model="gpt-4o-mini",
            operation="chat",
            messages=[{"role": "user", "content": "hi"}],
        ),
    )

    assert result.text == "hello"


def test_stream_invoke_yields_content_delta_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICompatibleProvider(_record())
    response = MagicMock()
    response.iter_lines.return_value = [
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(provider, "_request", MagicMock(return_value=response))

    events = list(
        provider.stream_invoke(
            LLMRequest(
                provider_id="test-gateway",
                model="gpt-4o-mini",
                operation="chat",
                messages=[{"role": "user", "content": "hi"}],
            ),
        ),
    )

    assert [event.type for event in events] == ["content_delta", "done"]
    assert events[0].data == "Hi"
