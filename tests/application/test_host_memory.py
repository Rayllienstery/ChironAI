from __future__ import annotations

from types import SimpleNamespace

import pytest

import application.host_memory as host_memory


def test_parse_docker_size_and_mem_and_pct() -> None:
    assert host_memory._parse_docker_size("") == 0
    assert host_memory._parse_docker_size("1.5GiB") == int(1.5 * 1024**3)
    assert host_memory._parse_docker_size("200MiB") == 200 * 1024**2
    used, limit = host_memory._parse_docker_mem("100MiB / 2GiB")
    assert used == 100 * 1024**2
    assert limit == 2 * 1024**3
    assert host_memory._parse_pct("12.5%") == 12.5
    assert host_memory._parse_pct("bad") is None
    assert host_memory._gb(1024**3) == 1.0
    assert host_memory._mb(10 * 1024**2) == 10.0


def test_script_from_cmdline_prefers_module_then_py_file() -> None:
    assert host_memory._script_from_cmdline("") == ""
    assert host_memory._script_from_cmdline("python -m webui_backend.rag_proxy") == "webui_backend.rag_proxy"
    assert host_memory._script_from_cmdline(r"C:\AI\scripts\phone_host\phone-host.ps1 python worker.py") == "worker.py"


def test_descendant_pids_walks_children(monkeypatch) -> None:
    monkeypatch.setattr(host_memory, "_iter_process_parents", lambda: [(1, 0), (2, 1), (3, 1), (4, 9)])
    assert host_memory._descendant_pids(1) == {1, 2, 3}


def test_collect_ram_metrics_combines_host_and_containers(monkeypatch) -> None:
    monkeypatch.setattr(
        host_memory,
        "_system_memory_detail",
        lambda: {
            "used_bytes": 8 * 1024**3,
            "total_bytes": 16 * 1024**3,
            "used_gb": 8.0,
            "total_gb": 16.0,
        },
    )
    monkeypatch.setattr(host_memory, "_descendant_pids", lambda _root: {1, 2})
    monkeypatch.setattr(host_memory, "_rss", lambda pid: 1000 if pid == 1 else 500)
    monkeypatch.setattr(host_memory, "_hermes_rss", lambda _pids: 250)
    monkeypatch.setattr(host_memory, "_managed_container_rss", lambda: 4000)

    snapshot = host_memory.collect_ram_metrics()

    assert snapshot["system_used_gb"] == 8.0
    assert snapshot["app_host_bytes"] == 1750
    assert snapshot["app_containers_bytes"] == 4000
    assert snapshot["app_bytes"] == 5750


def test_collect_gpu_snapshot_returns_none_without_nvidia(monkeypatch) -> None:
    monkeypatch.setattr(host_memory.shutil, "which", lambda _name: None)
    assert host_memory.collect_gpu_snapshot() is None


def test_gpu_snapshot_parses_nvidia_smi(monkeypatch) -> None:
    monkeypatch.setattr(host_memory.shutil, "which", lambda _name: "nvidia-smi")
    monkeypatch.setattr(host_memory.sys, "platform", "linux")
    monkeypatch.setattr(
        host_memory.subprocess,
        "run",
        lambda **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="RTX 5090, 572.16, 12, 8192, 24576, 61\n",
        ),
    )
    snapshot = host_memory.collect_gpu_snapshot()
    assert snapshot is not None
    assert snapshot["name"] == "RTX 5090"
    assert snapshot["utilization_pct"] == 12
    assert snapshot["memory_total_mb"] == 24576


def test_collect_performance_snapshot_sorts_processes(monkeypatch) -> None:
    monkeypatch.setattr(
        host_memory,
        "_system_memory_detail",
        lambda: {"used_bytes": 1, "total_bytes": 2, "used_gb": 0.0, "total_gb": 0.0},
    )
    monkeypatch.setattr(host_memory, "_iter_process_rows", lambda: [(11, 1, "python.exe")])
    monkeypatch.setattr(host_memory, "_descendant_pids", lambda _root: {11})
    monkeypatch.setattr(
        host_memory,
        "_host_process_rows",
        lambda _pids, _names: [
            {"id": "proc:11", "pid": 11, "rss_bytes": 100, "name": "python.exe"}
        ],
    )
    monkeypatch.setattr(
        host_memory,
        "_managed_container_rows",
        lambda: [{"id": "container:1", "pid": None, "rss_bytes": 300, "name": "qdrant"}],
    )
    monkeypatch.setattr(host_memory, "collect_gpu_snapshot", lambda: None)
    monkeypatch.setattr(
        "application.host_cpu.sample_cpu_pct",
        lambda pids: {int(pid): 1.5 for pid in pids},
    )

    snapshot = host_memory.collect_performance_snapshot()

    assert snapshot["processes"][0]["name"] == "qdrant"
    assert snapshot["app"]["bytes"] == 400
    assert snapshot["gpu"] is None


def test_managed_container_rows_parses_docker_listing(monkeypatch) -> None:
    host_memory._container_cache["at"] = 0.0
    host_memory._container_cache["rows"] = []
    listing = "abc123\tqdrant\tcom.chironai.managed=true\n"
    stats = "abc123\tqdrant\t10MiB / 1GiB\t2.0%\n"
    monkeypatch.setattr(host_memory, "_docker_run", lambda args, timeout: listing if args[0] == "ps" else stats)
    monkeypatch.setattr("docker_manager.manager.MANAGED_LABEL", "com.chironai.managed")

    rows = host_memory._managed_container_rows(use_cache=False)

    assert rows[0]["name"] == "qdrant"
    assert rows[0]["cpu_pct"] == 2.0
    assert rows[0]["rss_bytes"] == 10 * 1024**2


def test_host_process_rows_include_hermes_outside_tree(monkeypatch) -> None:
    monkeypatch.setattr(host_memory, "_rss", lambda pid: 111 if pid == 5 else 0)
    monkeypatch.setattr(
        "application.hermes_processes.collect_managed_processes",
        lambda: [
            {"id": "gateway", "label": "Gateway", "alive": True, "pid": 77, "rss_bytes": 222, "rss": "222 B"}
        ],
    )
    monkeypatch.setattr("application.hermes_processes.read_process_cmdline", lambda _pid: "python -m webui_backend.rag_proxy")
    rows = host_memory._host_process_rows({5}, {5: "python.exe"})
    names = {row["name"] for row in rows}
    assert "python.exe" in names or any(row["pid"] == 5 for row in rows)
    assert any(row["pid"] == 77 for row in rows)


def test_format_rss_fallback_on_import_error(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "application.hermes_processes":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert "MB" in host_memory._format_rss(12 * 1024**2) or host_memory._format_rss(12 * 1024**2).endswith("B")


def test_win_dll_raises_when_loader_missing() -> None:
    import ctypes
    import sys

    if sys.platform == "win32":
        assert host_memory._win_dll("kernel32") is not None
        return
    assert getattr(ctypes, "WinDLL", None) is None
    with pytest.raises(OSError):
        host_memory._win_dll("kernel32")
