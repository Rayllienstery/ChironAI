from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.openai_compatible_provider import OpenAICompatibleProvider


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
