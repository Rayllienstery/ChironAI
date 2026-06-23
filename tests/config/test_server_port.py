from __future__ import annotations

import config


class _SettingsRepo:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get_app_setting(self, key: str) -> str | None:
        return self.values.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.values[key] = value


def test_server_port_metadata_falls_back_to_yaml_config(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8123)

    metadata = config.get_server_port_metadata(_SettingsRepo())

    assert metadata["server_port"] == 8123
    assert metadata["server_port_source"] == "config"
    assert metadata["server_port_active"] == 8123
    assert metadata["server_port_restart_required"] is False


def test_server_port_metadata_uses_app_settings_before_config(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8123)

    metadata = config.get_server_port_metadata(_SettingsRepo({"server_port": "9000"}))

    assert metadata["server_port"] == 9000
    assert metadata["server_port_source"] == "settings"


def test_server_port_metadata_env_overrides_app_settings(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9100")
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)

    metadata = config.get_server_port_metadata(_SettingsRepo({"server_port": "9000"}))

    assert metadata["server_port"] == 9100
    assert metadata["server_port_source"] == "env"


def test_invalid_saved_server_port_is_ignored(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8123)

    metadata = config.get_server_port_metadata(_SettingsRepo({"server_port": "70000"}))

    assert metadata["server_port"] == 8123
    assert metadata["server_port_source"] == "config"


def test_server_port_candidates_include_saved_and_last_active(monkeypatch):
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv(config.ACTIVE_SERVER_PORT_ENV, raising=False)
    monkeypatch.setitem(config.SERVER_CONFIG, "port", 8080)
    repo = _SettingsRepo({"server_port": "9000", "server_port_last_active": "8080"})

    candidates = config.get_server_port_candidate_ports(repo)

    assert candidates[:2] == [9000, 8080]
