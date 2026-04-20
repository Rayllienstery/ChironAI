from __future__ import annotations

from types import SimpleNamespace


def test_update_path_entries_idempotent_case_insensitive() -> None:
    from api.http import webui_routes as wr

    updated, changed = wr._update_path_entries(
        [r"C:\Users\Me\.chironai\bin", r"C:\Other"],
        r"c:\users\me\.CHIRONAI\BIN",
        prepend=False,
    )
    assert changed is False
    assert updated == [r"C:\Users\Me\.chironai\bin", r"C:\Other"]


def test_update_path_entries_prepends_existing_entry() -> None:
    from api.http import webui_routes as wr

    updated, changed = wr._update_path_entries(
        [r"C:\Other", r"C:\Users\Me\.chironai\bin"],
        r"c:\users\me\.chironai\bin",
        prepend=True,
    )
    assert changed is True
    assert updated[0] == r"C:\Users\Me\.chironai\bin"


def test_compute_global_status_requires_shim_precedence(monkeypatch, tmp_path) -> None:
    from api.http import webui_routes as wr

    shim_dir = tmp_path / ".chironai" / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "codex.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")

    monkeypatch.setattr(wr, "_get_chiron_shim_dir", lambda: str(shim_dir))
    monkeypatch.setattr(wr, "_get_chiron_codex_shim_path", lambda: str(shim))
    monkeypatch.setattr(wr, "_get_windows_user_path", lambda: f"{shim_dir};C:\\Other")

    def _fake_where(name: str, env=None):  # noqa: ARG001
        if name == "codex":
            return [str(shim), r"C:\Users\Me\AppData\Roaming\npm\codex.cmd"], ""
        if name == "chironai":
            return [r"C:\Users\Me\AppData\Roaming\Python\Python314\Scripts\chironai.exe"], ""
        return [], ""

    monkeypatch.setattr(wr, "_run_cmd_where", _fake_where)
    monkeypatch.setattr(
        wr.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    status = wr._compute_global_status_diagnostics()
    assert status["is_global"] is True
    assert status["codex_first_is_shim"] is True
    assert status["mismatch_reasons"] == []


def test_compute_global_status_reports_wrong_first_hit(monkeypatch, tmp_path) -> None:
    from api.http import webui_routes as wr

    shim_dir = tmp_path / ".chironai" / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "codex.cmd"
    shim.write_text("@echo off\r\n", encoding="utf-8")

    monkeypatch.setattr(wr, "_get_chiron_shim_dir", lambda: str(shim_dir))
    monkeypatch.setattr(wr, "_get_chiron_codex_shim_path", lambda: str(shim))
    monkeypatch.setattr(wr, "_get_windows_user_path", lambda: f"{shim_dir};C:\\Other")

    def _fake_where(name: str, env=None):  # noqa: ARG001
        if name == "codex":
            return [r"C:\Users\Me\AppData\Roaming\npm\codex.cmd", str(shim)], ""
        if name == "chironai":
            return [r"C:\Users\Me\AppData\Roaming\Python\Python314\Scripts\chironai.exe"], ""
        return [], ""

    monkeypatch.setattr(wr, "_run_cmd_where", _fake_where)
    monkeypatch.setattr(
        wr.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    status = wr._compute_global_status_diagnostics()
    assert status["is_global"] is False
    assert status["codex_first_is_shim"] is False
    assert any("PATH precedence wrong" in x for x in status["mismatch_reasons"])


def test_build_status_cmd_env_prepends_registry_user_path(monkeypatch) -> None:
    from api.http import webui_routes as wr

    monkeypatch.setattr(wr, "os", wr.os)
    monkeypatch.setattr(wr.os, "name", "nt")
    monkeypatch.setattr(wr, "_get_windows_user_path", lambda: r"C:\Users\Me\.chironai\bin;C:\Users\Me\AppData\Roaming\npm")

    original_path = wr.os.environ.get("Path")
    wr.os.environ["Path"] = r"C:\Windows\System32;C:\Other"
    try:
        env = wr._build_status_cmd_env()
        assert env is not None
        assert env["Path"].startswith(r"C:\Users\Me\.chironai\bin;")
    finally:
        if original_path is None:
            wr.os.environ.pop("Path", None)
        else:
            wr.os.environ["Path"] = original_path
