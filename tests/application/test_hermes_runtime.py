from __future__ import annotations

from pathlib import Path

import application.hermes_runtime as hermes_runtime
from application.hermes_runtime import (
    HermesRuntime,
    bind_lifecycle_to_host,
    reset_lifecycle_for_tests,
    stop_bound_gateway,
)


def test_inspect_reports_missing_binary(tmp_path: Path) -> None:
    runtime = HermesRuntime(
        which=lambda _name: None,
        run_cli=lambda _args, _timeout: {"ok": False, "stdout": "", "stderr": ""},
        health_probe=lambda _url: {"ok": False, "http_status": None},
        login_path=tmp_path / "missing.vbs",
        home=tmp_path,
        list_processes=lambda: [],
    )

    status = runtime.inspect()

    assert status["installed"] is False
    assert status["running"] is False
    assert status["tone"] == "warning"
    assert "not installed" in str(status["message"]).lower()


def test_ensure_adopts_running_gateway_and_removes_login_item(tmp_path: Path) -> None:
    login = tmp_path / "Hermes_Gateway.vbs"
    login.write_text("login", encoding="utf-8")
    calls: list[list[str]] = []

    def run_cli(args: list[str], _timeout: float) -> dict[str, object]:
        calls.append(list(args))
        if args[:2] == ["gateway", "status"]:
            return {"ok": True, "stdout": "Gateway process running (PID: 42)\n", "stderr": ""}
        if args[:2] == ["gateway", "uninstall"]:
            return {"ok": True, "stdout": "uninstalled", "stderr": ""}
        if args == ["--version"]:
            return {"ok": True, "stdout": "0.20.6\n", "stderr": ""}
        return {"ok": True, "stdout": "", "stderr": ""}

    spawned: list[list[str]] = []
    runtime = HermesRuntime(
        which=lambda _name: str(tmp_path / "hermes.exe"),
        run_cli=run_cli,
        spawn_gateway=lambda args: spawned.append(list(args)) or {"ok": True, "pid": 99},
        health_probe=lambda _url: {"ok": True, "http_status": 200, "body": "{}"},
        login_path=login,
        home=tmp_path,
        list_processes=lambda: [],
    )
    (tmp_path / "hermes.exe").write_text("stub", encoding="utf-8")

    result = runtime.ensure()

    assert result["ok"] is True
    assert result["status"]["running"] is True
    assert spawned == []
    assert ["gateway", "uninstall"] in calls
    assert login.is_file() is False


def test_ensure_spawns_gateway_run_when_stopped(tmp_path: Path) -> None:
    spawned: list[list[str]] = []
    healthy = {"ok": False}

    def health(_url: str) -> dict[str, object]:
        return {"ok": healthy["ok"], "http_status": 200 if healthy["ok"] else None}

    def run_cli(args: list[str], _timeout: float) -> dict[str, object]:
        if args[:2] == ["gateway", "status"]:
            return {"ok": True, "stdout": "stopped\n", "stderr": ""}
        if args == ["--version"]:
            return {"ok": True, "stdout": "0.20.6\n", "stderr": ""}
        return {"ok": True, "stdout": "", "stderr": ""}

    def spawn(args: list[str]) -> dict[str, object]:
        spawned.append(list(args))
        healthy["ok"] = True
        return {"ok": True, "pid": 7}

    runtime = HermesRuntime(
        which=lambda _name: str(tmp_path / "hermes.exe"),
        run_cli=run_cli,
        spawn_gateway=spawn,
        health_probe=health,
        login_path=tmp_path / "missing.vbs",
        home=tmp_path,
        list_processes=lambda: [],
    )
    (tmp_path / "hermes.exe").write_text("stub", encoding="utf-8")

    result = runtime.ensure()

    assert result["ok"] is True
    assert spawned == [["gateway", "run"]]
    assert result["status"]["running"] is True


def test_stop_and_update_use_cli(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    state = {"running": True}

    def run_cli(args: list[str], _timeout: float) -> dict[str, object]:
        calls.append(list(args))
        if args[:2] == ["gateway", "stop"]:
            state["running"] = False
            return {"ok": True, "stdout": "stopped", "stderr": ""}
        if args == ["update"]:
            return {"ok": True, "stdout": "updated\n", "stderr": ""}
        if args[:2] == ["gateway", "status"]:
            marker = "Gateway process running (PID: 8)\n" if state["running"] else "stopped\n"
            return {"ok": True, "stdout": marker, "stderr": ""}
        if args == ["--version"]:
            return {"ok": True, "stdout": "0.20.6\n", "stderr": ""}
        return {"ok": True, "stdout": "", "stderr": ""}

    def health(_url: str) -> dict[str, object]:
        return {"ok": state["running"], "http_status": 200 if state["running"] else None}

    def spawn(args: list[str]) -> dict[str, object]:
        state["running"] = True
        return {"ok": True, "pid": 1}

    runtime = HermesRuntime(
        which=lambda _name: str(tmp_path / "hermes.exe"),
        run_cli=run_cli,
        spawn_gateway=spawn,
        health_probe=health,
        login_path=tmp_path / "missing.vbs",
        home=tmp_path,
        list_processes=lambda: [],
    )
    (tmp_path / "hermes.exe").write_text("stub", encoding="utf-8")

    stopped = runtime.stop()
    assert stopped["ok"] is True
    assert state["running"] is False
    assert ["gateway", "stop"] in calls

    state["running"] = True
    updated = runtime.update()
    assert updated["ok"] is True
    assert ["update"] in calls


def test_bound_lifecycle_stop_is_noop_until_bound(monkeypatch) -> None:
    reset_lifecycle_for_tests()
    called = {"stop": 0}

    class _Runtime:
        def stop(self) -> dict[str, object]:
            called["stop"] += 1
            return {"ok": True}

        def ensure(self) -> dict[str, object]:
            return {"ok": True, "message": "started"}

    monkeypatch.setattr(hermes_runtime, "HermesRuntime", _Runtime)
    assert stop_bound_gateway() is None
    bind_lifecycle_to_host()
    assert stop_bound_gateway() == {"ok": True}
    assert called["stop"] == 1
    reset_lifecycle_for_tests()


def test_windows_spawn_flags_break_away_from_job(monkeypatch) -> None:
    monkeypatch.setattr(hermes_runtime.sys, "platform", "win32")
    flags = hermes_runtime._windows_creation_flags(breakaway=True)
    assert flags & hermes_runtime.CREATE_NO_WINDOW
    assert flags & hermes_runtime.CREATE_NEW_PROCESS_GROUP
    assert flags & hermes_runtime.CREATE_BREAKAWAY_FROM_JOB
    cli_flags = hermes_runtime._windows_creation_flags(hide_only=True, breakaway=True)
    assert cli_flags & hermes_runtime.CREATE_NO_WINDOW
    assert not (cli_flags & hermes_runtime.CREATE_BREAKAWAY_FROM_JOB)
