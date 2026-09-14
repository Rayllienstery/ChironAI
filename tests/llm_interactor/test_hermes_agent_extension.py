from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_hermes_provider_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "extensions" / "bundled" / "hermes-agent" / "backend" / "provider.py"
    spec = importlib.util.spec_from_file_location("test_hermes_agent_extension_provider", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Repo:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get_app_setting(self, key: str):
        return self.data.get(key)

    def set_app_setting(self, key: str, value: str) -> None:
        self.data[key] = value


class _Hermes:
    def __init__(self) -> None:
        self.running = False
        self.installed = True
        self.ensured = 0
        self.stopped = 0
        self.updated = 0
        self.dashboard_ensured = 0

    def inspect(self) -> dict[str, Any]:
        return {
            "ok": self.installed,
            "installed": self.installed,
            "running": self.running,
            "tone": "success" if self.running else "neutral" if self.installed else "warning",
            "message": "running" if self.running else "stopped" if self.installed else "not installed",
            "pid": 42 if self.running else None,
            "binary": r"C:\Users\Raylee\AppData\Local\hermes\bin\hermes.exe" if self.installed else "",
            "version": "0.20.6" if self.installed else "",
            "health_url": "http://127.0.0.1:8642/health",
            "dashboard_url": "http://127.0.0.1:9119/",
            "http_status": 200 if self.running else None,
            "login_autostart": False,
            "install_url": "https://hermes-agent.nousresearch.com/",
        }

    def ensure(self) -> dict[str, Any]:
        self.ensured += 1
        self.running = True
        return {"ok": True, "message": "Gateway started", "status": self.inspect()}

    def stop(self) -> dict[str, Any]:
        self.stopped += 1
        self.running = False
        return {"ok": True, "message": "Gateway stopped", "status": self.inspect()}

    def update(self) -> dict[str, Any]:
        self.updated += 1
        return {"ok": True, "message": "updated", "status": self.inspect()}

    def ensure_dashboard(self, open_browser: bool = False) -> dict[str, Any]:
        self.dashboard_ensured += 1
        return {
            "ok": True,
            "message": "http://127.0.0.1:9119/",
            "dashboard_url": "http://127.0.0.1:9119/",
            "status": self.inspect(),
        }


def _extension(hermes: _Hermes | None = None):
    mod = _load_hermes_provider_module()
    host = SimpleNamespace(
        get_settings_repository=lambda: _Repo(),
        hermes_runtime=hermes if hermes is not None else _Hermes(),
    )
    manifest = SimpleNamespace(
        id="hermes-agent",
        title="Hermes",
        description="",
        icon="icons/hermes-agent-light.svg",
        tab_ui={
            "id": "hermes-agent",
            "title": "Hermes",
            "icon": "icons/hermes-agent-light.svg",
            "order": 62,
        },
        metadata={},
    )
    return mod.HermesAgentExtension(host, manifest), mod, host


def test_hermes_agent_tab_payload_and_actions() -> None:
    hermes = _Hermes()
    ext, _mod, _host = _extension(hermes)

    descriptor = ext.get_tab_descriptor()
    payload = ext.get_tab_payload()

    assert descriptor["id"] == "hermes-agent"
    assert descriptor["title"] == "Hermes"
    assert descriptor["icon"] == "icons/hermes-agent-light.svg"
    assert descriptor["status"]["running"] is False
    assert payload["content"]["type"] == "service_panel"
    assert payload["content"]["subtitle"] == "Host-managed Hermes Agent gateway"
    assert payload["content"]["open_external_url"] == "http://127.0.0.1:9119/"
    assert payload["content"]["service"]["metaColumns"] == 2
    action_ids = {a["id"] for a in payload["content"]["actions"]}
    assert {"refresh", "update", "start", "open_external"} <= action_ids
    assert "stop" not in action_ids
    labels = [item["label"] for item in payload["content"]["details"]]
    assert "Binary" in labels
    assert "Gateway" in labels
    assert "Dashboard" in labels
    assert "RAM total" in labels
    assert "Health URL" in labels
    assert "Dashboard URL" in labels
    assert "Login autostart" in labels

    started = ext.run_action("start", {})
    assert started["ok"] is True
    assert hermes.ensured == 1
    assert hermes.running is True

    payload_running = ext.get_tab_payload()
    running_ids = {a["id"] for a in payload_running["content"]["actions"]}
    assert "stop" in running_ids
    assert "start" not in running_ids

    stopped = ext.run_action("stop", {})
    assert stopped["ok"] is True
    assert hermes.stopped == 1
    updated = ext.run_action("update", {})
    assert updated["ok"] is True
    assert hermes.updated == 1
    refreshed = ext.run_action("refresh", {})
    assert refreshed["ok"] is True
    opened = ext.run_action("open_external", {})
    assert opened["ok"] is True
    assert opened["open_external_url"] == "http://127.0.0.1:9119/"
    assert hermes.dashboard_ensured == 1


def test_hermes_agent_reports_missing_runtime() -> None:
    mod = _load_hermes_provider_module()
    host = SimpleNamespace(get_settings_repository=lambda: _Repo(), hermes_runtime=None)
    manifest = SimpleNamespace(id="hermes-agent", title="Hermes", icon="icons/hermes-agent-light.svg", metadata={})
    ext = mod.HermesAgentExtension(host, manifest)

    payload = ext.get_tab_payload()
    assert payload["status"]["tone"] == "error"
    result = ext.run_action("start", {})
    assert result["ok"] is False
    assert "unavailable" in str(result["message"]).lower()
