from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, Flask

import config

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


class _SettingsRepo:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get_all_app_settings(self) -> dict[str, str]:
        return dict(self.values)

    def get_app_setting(self, key: str) -> str | None:
        return self.values.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.values[key] = value


def _client(monkeypatch, repo: _SettingsRepo):
    import api.http.webui_settings_routes as routes

    monkeypatch.setattr(routes, "get_settings_repository", lambda: repo)
    app = Flask(__name__)
    bp = Blueprint("webui_settings_test", __name__, url_prefix="/api/webui")
    routes.register_settings_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
        keyword_collections_repository_factory=None,
        get_effective_rag_trigger_threshold=lambda: 2,
        trigger_help_rows=[],
    )
    app.register_blueprint(bp)
    return app.test_client()


def test_settings_get_returns_server_port_metadata(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.setenv(config.ACTIVE_SERVER_PORT_ENV, "8080")
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8080)
    repo = _SettingsRepo({"server_port": "9000"})

    data = _client(monkeypatch, repo).get("/api/webui/settings").get_json()

    assert data["server_port"] == 9000
    assert data["server_port_active"] == 8080
    assert data["server_port_source"] == "settings"
    assert data["server_port_restart_required"] is True


def test_settings_post_persists_valid_server_port(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8080)
    repo = _SettingsRepo()

    response = _client(monkeypatch, repo).post("/api/webui/settings", json={"server_port": 9000})

    assert response.status_code == 200
    assert repo.values["server_port"] == "9000"
    assert response.get_json()["server_port"] == 9000


def test_settings_post_rejects_invalid_server_port_without_persisting(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8080)
    repo = _SettingsRepo({"server_port": "9000"})

    response = _client(monkeypatch, repo).post("/api/webui/settings", json={"server_port": 70000})

    assert response.status_code == 400
    assert repo.values["server_port"] == "9000"
