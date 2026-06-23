"""
Light integration tests for HTTP endpoints (Flask test client).

Domain-specific suites: ``test_http_health``, ``test_http_proxy_auth``,
``test_http_observability``, ``test_http_llm_proxy_builds``, ``test_http_chat_completions``,
``test_http_v1_models``, ``test_http_extensions``.
Shared fixtures: ``tests.api.http_fixtures``.
"""

from __future__ import annotations

import pytest

from tests.api.http_fixtures import (
    webui_blueprint_client as _webui_blueprint_client,
)


def test_rag_trigger_settings_uses_registered_threshold_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.http.webui_routes as webui_routes

    class FakeSettingsRepo:
        def get_app_setting(self, key: str):
            return "9" if key == "rag_trigger_threshold" else None

    monkeypatch.setattr(webui_routes, "get_settings_repository", lambda: FakeSettingsRepo())

    response = _webui_blueprint_client().get("/api/webui/rag-trigger-settings")

    assert response.status_code == 200
    assert response.get_json()["rag_trigger_threshold"] == 9

