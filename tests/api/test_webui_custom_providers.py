from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Blueprint, Flask

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


class _MemSettingsRepo:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_app_setting(self, key: str) -> str | None:
        return self._data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self._data[key] = value


def _client(repo: _MemSettingsRepo | None = None):
    import api.http.webui_providers_routes as routes

    settings_repo = repo or _MemSettingsRepo()
    app = Flask(__name__)
    bp = Blueprint("webui_providers_test", __name__, url_prefix="/api/webui")
    routes.register_providers_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
        settings_repository_factory=lambda: settings_repo,
    )
    app.register_blueprint(bp)
    return app.test_client(), settings_repo


def test_list_custom_providers_empty() -> None:
    client, _repo = _client()
    data = client.get("/api/webui/providers/custom").get_json()
    assert data == {"providers": []}


def test_create_update_delete_custom_provider() -> None:
    client, _repo = _client()
    created = client.post(
        "/api/webui/providers/custom",
        json={
            "id": "my-gateway",
            "display_name": "My Gateway",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-secret-key",
            "manual_models": ["gpt-4o-mini"],
        },
    )
    assert created.status_code == 201
    payload = created.get_json()
    assert payload["id"] == "my-gateway"
    assert payload["api_key_configured"] is True
    assert "sk-t" in str(payload.get("api_key_masked") or "")

    listed = client.get("/api/webui/providers/custom").get_json()
    assert len(listed["providers"]) == 1

    updated = client.put(
        "/api/webui/providers/custom/my-gateway",
        json={
            "display_name": "Renamed Gateway",
            "base_url": "https://api.example.com/v1",
            "enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["display_name"] == "Renamed Gateway"
    assert updated.get_json()["enabled"] is False

    deleted = client.delete("/api/webui/providers/custom/my-gateway")
    assert deleted.status_code == 200
    assert client.get("/api/webui/providers/custom").get_json()["providers"] == []


def test_create_custom_provider_requires_api_key() -> None:
    client, _repo = _client()
    response = client.post(
        "/api/webui/providers/custom",
        json={
            "id": "no-key",
            "base_url": "https://api.example.com",
        },
    )
    assert response.status_code == 400
    assert "api_key" in response.get_json()["error"].lower()


def test_test_custom_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _repo = _client()
    client.post(
        "/api/webui/providers/custom",
        json={
            "id": "testable",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-testable-key",
        },
    )

    mock_provider = MagicMock()
    mock_provider.test_connection.return_value = {
        "ok": True,
        "status": "ok",
        "message": "",
        "model_count": 2,
        "models": [{"id": "gpt-4o-mini", "label": "gpt-4o-mini"}],
    }
    monkeypatch.setattr(
        "api.http.webui_providers_routes.OpenAICompatibleProvider",
        lambda record: mock_provider,
    )

    response = client.post("/api/webui/providers/custom/testable/test")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.get_json()["model_count"] == 2
