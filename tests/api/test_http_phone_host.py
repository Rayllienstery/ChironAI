"""GET /api/webui/host/phone-status compact Shortcut payload."""

from __future__ import annotations

from typing import Any

import pytest

from application.phone_host_status import build_phone_host_status


def test_build_phone_host_status_idle() -> None:
    payload = build_phone_host_status([], {"utilization_pct": 3}, proxy_status="Idle")
    assert payload["host"] == "awake"
    assert payload["chiron"] == "up"
    assert payload["generating"] is False
    assert payload["kind"] is None
    assert payload["gpu_pct"] == 3
    assert payload["message"] == "PC awake, Chiron idle"


def test_build_phone_host_status_llm_trace_beats_gpu() -> None:
    traces = [
        {
            "request": {"actual_model": "qwen3"},
            "provider": {"tokens_estimates": {"completion_tokens_estimated": 412}},
        }
    ]
    payload = build_phone_host_status(traces, {"utilization_pct": 90}, proxy_status="Response")
    assert payload["generating"] is True
    assert payload["kind"] == "llm"
    assert payload["detail"] == "qwen3 · 412 tok"
    assert payload["active_traces"] == 1


def test_build_phone_host_status_gpu_only() -> None:
    payload = build_phone_host_status([], {"utilization_pct": 87}, gpu_busy_pct=15)
    assert payload["generating"] is True
    assert payload["kind"] == "gpu"
    assert payload["detail"] == "GPU 87%"
    assert "GPU 87%" in payload["message"]


def _client(monkeypatch: pytest.MonkeyPatch, *, traces: list[dict[str, Any]] | None = None, gpu: dict[str, Any] | None = None):
    import api.http.webui_phone_host_routes as routes
    from api.http.rag_routes import create_app

    monkeypatch.setattr(routes, "get_active_traces", lambda: list(traces or []))
    monkeypatch.setattr(routes, "collect_gpu_snapshot", lambda: gpu)
    monkeypatch.setattr(routes, "get_proxy_status_label", lambda: "Idle")
    return create_app(bootstrap_extensions=False).test_client()


def test_phone_status_loopback_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, traces=[], gpu={"utilization_pct": 1})
    response = client.get("/api/webui/host/phone-status")
    assert response.status_code == 200
    data = response.get_json() or {}
    assert data["host"] == "awake"
    assert data["chiron"] == "up"
    assert data["generating"] is False


def test_phone_status_remote_without_token_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHIRONAI_PHONE_STATUS_TOKEN", raising=False)
    client = _client(monkeypatch)
    response = client.get(
        "/api/webui/host/phone-status",
        environ_base={"REMOTE_ADDR": "192.168.50.20"},
    )
    assert response.status_code == 403


def test_phone_status_remote_with_token_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHIRONAI_PHONE_STATUS_TOKEN", "shortcut-secret")
    client = _client(
        monkeypatch,
        traces=[{"request": {"requested_model": "glm"}, "provider": {}}],
        gpu={"utilization_pct": 4},
    )
    response = client.get(
        "/api/webui/host/phone-status",
        headers={"X-Chiron-Phone-Token": "shortcut-secret"},
        environ_base={"REMOTE_ADDR": "192.168.50.20"},
    )
    assert response.status_code == 200
    data = response.get_json() or {}
    assert data["generating"] is True
    assert data["kind"] == "llm"
    assert data["detail"] == "glm"


def _install_script_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    scripts_dir = tmp_path / "phone_host"
    scripts_dir.mkdir()
    (scripts_dir / "phone-host.ps1").write_text("#", encoding="utf-8")
    (scripts_dir / "phone-host.cmd").write_text("@echo off\n", encoding="utf-8")
    (scripts_dir / "setup-openssh.ps1").write_text("#", encoding="utf-8")

    class MemRepo:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def get_app_setting(self, key: str) -> str | None:
            return self.store.get(key)

        def set_app_setting(self, key: str, value: str) -> None:
            self.store[key] = value

    repo = MemRepo()
    import api.http.webui_phone_host_routes as routes
    import application.phone_host_scripts as scripts

    monkeypatch.setattr(scripts, "phone_host_scripts_dir", lambda: scripts_dir)
    monkeypatch.setattr(scripts, "phone_host_enabled_path", lambda: scripts_dir / "enabled.json")
    monkeypatch.setattr(routes, "get_settings_repository", lambda: repo)
    return scripts_dir, repo


def test_phone_scripts_list_defaults_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _install_script_dir(monkeypatch, tmp_path)
    from api.http.rag_routes import create_app

    client = create_app(bootstrap_extensions=False).test_client()
    response = client.get("/api/webui/host/phone-scripts")
    assert response.status_code == 200
    rows = (response.get_json() or {}).get("scripts") or []
    ids = [row["id"] for row in rows]
    assert ids == ["phone-host", "setup-openssh"]
    assert all(row["enabled"] is True for row in rows)
    assert all(row["exists"] is True for row in rows)


def test_phone_scripts_can_disable(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    scripts_dir, _repo = _install_script_dir(monkeypatch, tmp_path)
    from api.http.rag_routes import create_app

    client = create_app(bootstrap_extensions=False).test_client()
    response = client.put(
        "/api/webui/host/phone-scripts/phone-host",
        json={"enabled": False},
    )
    assert response.status_code == 200
    rows = {row["id"]: row for row in (response.get_json() or {}).get("scripts") or []}
    assert rows["phone-host"]["enabled"] is False
    assert rows["setup-openssh"]["enabled"] is True
    saved = (scripts_dir / "enabled.json").read_text(encoding="utf-8")
    assert '"phone-host": false' in saved


def test_phone_scripts_unknown_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _install_script_dir(monkeypatch, tmp_path)
    from api.http.rag_routes import create_app

    client = create_app(bootstrap_extensions=False).test_client()
    response = client.put("/api/webui/host/phone-scripts/nope", json={"enabled": True})
    assert response.status_code == 404
