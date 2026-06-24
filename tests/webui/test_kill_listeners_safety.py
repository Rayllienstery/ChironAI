"""Subprocess safety in WebUI backend helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from webui_backend.kill_listeners_on_config_port import _kill_port


@pytest.mark.skipif("sys.platform != 'win32'", reason="Windows-only helper")
def test_kill_port_uses_which_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    run_calls: list[tuple[Any, ...]] = []

    def _fake_run(*args: Any, **kwargs: Any) -> Any:
        run_calls.append((args, kwargs))
        class _R:
            stdout = "  TCP    127.0.0.1:8080    0.0.0.0:0    LISTENING    1234\n"
            returncode = 0
        return _R()

    monkeypatch.setattr("subprocess.run", _fake_run)
    monkeypatch.setattr("shutil.which", lambda name: f"C:\\Windows\\System32\\{name}.exe")

    _kill_port(8080)

    assert len(run_calls) == 2
    assert run_calls[0][0] == (["C:\\Windows\\System32\\netstat.exe", "-ano", "-p", "TCP"],)
    assert run_calls[1][0] == (["C:\\Windows\\System32\\taskkill.exe", "/F", "/PID", "1234"],)


def test_kill_port_returns_when_netstat_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    run_calls: list[tuple[Any, ...]] = []

    def _fake_run(*args: Any, **kwargs: Any) -> Any:
        run_calls.append((args, kwargs))
        return None

    monkeypatch.setattr("subprocess.run", _fake_run)
    monkeypatch.setattr("shutil.which", lambda name: None)

    _kill_port(8080)

    assert run_calls == []
