"""HTTP tests for WebUI chat and model list routes."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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


def _client(
    *,
    catalog: dict | None = None,
    settings_repo: _MemSettingsRepo | None = None,
    proxy_runner=None,
):
    import api.http.webui_chat_routes as routes

    settings_repo = settings_repo or _MemSettingsRepo()
    app = Flask(__name__)
    bp = Blueprint("webui_chat_test", __name__, url_prefix="/api/webui")
    routes.register_chat_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
        provider_catalog_payload=lambda capability="chat": catalog
        or {
            "models": [
                {
                    "id": "llama3",
                    "provider_id": "ollama",
                    "label": "Llama 3",
                    "description": "local",
                }
            ]
        },
        default_llm_provider_id=lambda: "ollama",
        config_default_chat_model=lambda: "llama3",
        run_unified_proxy_chat=proxy_runner or (lambda body: ({"ok": True, "body": body}, 200)),
        set_proxy_status=lambda _status: None,
        set_latest_request_seconds=lambda _seconds: None,
    )
    app.register_blueprint(bp)
    return app.test_client(), settings_repo


def test_get_models_returns_catalog_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.http.webui_chat_routes.get_settings_repository", lambda: _MemSettingsRepo())
    client, _repo = _client()
    data = client.get("/api/webui/models").get_json()
    assert data["models"][0]["id"] == "llama3"
    assert data["models"][0]["provider_id"] == "ollama"


def test_get_models_inserts_autocomplete_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _MemSettingsRepo()
    repo.set_app_setting("proxy_autocomplete_model", "fast-inline")
    repo.set_app_setting("proxy_autocomplete_provider_id", "ollama")
    monkeypatch.setattr("api.http.webui_chat_routes.get_settings_repository", lambda: repo)
    client, _repo = _client(settings_repo=repo)
    data = client.get("/api/webui/models").get_json()
    assert data["models"][0]["id"] == "ChironAI-Autocomplete"


def test_get_config_returns_rag_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.http.webui_chat_routes.get_rag_int", lambda key, default: default)
    monkeypatch.setattr("api.http.webui_chat_routes.get_rag_float", lambda key, default: default)
    client, _repo = _client()
    data = client.get("/api/webui/config").get_json()
    assert data["top_k"] == 4
    assert data["model_name"] == "llama3"


def test_chat_requires_messages() -> None:
    client, _repo = _client()
    response = client.post("/api/webui/chat", json={})
    assert response.status_code == 400
    assert "messages" in response.get_json()["error"]["message"].lower()


def test_chat_forwards_body_to_proxy_runner() -> None:
    captured: dict = {}

    def _runner(body):
        captured.update(body)
        from flask import jsonify

        return jsonify({"answer": "ok"})

    client, _repo = _client(proxy_runner=_runner)
    response = client.post(
        "/api/webui/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    assert captured["messages"][0]["content"] == "hello"
    assert captured["include_rag_metadata"] is True


def test_chat_code_only_prefixes_last_user_message() -> None:
    captured: dict = {}

    def _runner(body):
        captured.update(body)
        from flask import jsonify

        return jsonify({"answer": "ok"})

    client, _repo = _client(proxy_runner=_runner)
    client.post(
        "/api/webui/chat",
        json={
            "code_only": True,
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "second"},
            ],
        },
    )
    assert captured["messages"][-1]["content"].startswith("Only code, no explanations.")


def test_dev_console_returns_recent_requests() -> None:
    client, _repo = _client()
    data = client.get("/api/webui/dev-console?limit=5").get_json()
    assert "requests" in data
    assert isinstance(data["requests"], list)
