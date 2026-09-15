from __future__ import annotations

from application.hermes_processes import (
    _role_for_cmdline,
    _tree_for_pid,
    collect_managed_processes,
    empty_managed_processes,
    format_rss,
)


def test_format_rss_scales_units() -> None:
    assert format_rss(0) == "0 B"
    assert format_rss(512) == "512 B"
    assert format_rss(2048) == "2 KB"
    assert format_rss(5 * 1024**2) == "5.0 MB"
    assert format_rss(20 * 1024**2) == "20 MB"
    assert format_rss(3 * 1024**3) == "3.0 GB"
    assert format_rss(12 * 1024**3) == "12 GB"


def test_role_for_cmdline_detects_gateway_and_dashboard() -> None:
    assert _role_for_cmdline("C:\\bin\\notepad.exe") is None
    assert _role_for_cmdline("hermes dashboard") == "dashboard"
    assert _role_for_cmdline("hermes.exe gateway run") == "gateway"
    assert _role_for_cmdline("hermes.exe doctor") is None


def test_tree_for_pid_walks_parents_to_hermes_root() -> None:
    rows = [
        {"pid": 1, "ppid": 0, "name": "hermes.exe", "rss": 10, "cmdline": "hermes gateway run"},
        {"pid": 2, "ppid": 1, "name": "python.exe", "rss": 4, "cmdline": "python -m worker"},
        {"pid": 9, "ppid": 0, "name": "other", "rss": 1, "cmdline": "other"},
    ]

    tree = _tree_for_pid(2, rows)

    assert {int(row["pid"]) for row in tree} == {1, 2}


def test_collect_managed_processes_groups_posix_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "application.hermes_processes._iter_posix_processes",
        lambda: [
            {
                "pid": 11,
                "ppid": 1,
                "name": "hermes",
                "rss": 1024,
                "cmdline": "hermes gateway run",
            },
            {
                "pid": 12,
                "ppid": 1,
                "name": "hermes",
                "rss": 2048,
                "cmdline": "hermes dashboard",
            },
        ],
    )
    monkeypatch.setattr("application.hermes_processes.sys.platform", "linux")

    rows = collect_managed_processes()

    assert rows[0]["alive"] is True
    assert rows[0]["pid"] == 11
    assert rows[1]["alive"] is True
    assert rows[1]["pid"] == 12


def test_collect_managed_processes_returns_empty_on_snapshot_error(monkeypatch) -> None:
    monkeypatch.setattr("application.hermes_processes.sys.platform", "linux")
    monkeypatch.setattr(
        "application.hermes_processes._iter_posix_processes",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert collect_managed_processes() == empty_managed_processes()
