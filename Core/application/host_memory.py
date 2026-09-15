"""System and ChironAI RAM snapshot for the CoreUI header and Performance Details."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any

_log = logging.getLogger("chironai.host_memory")

_DOCKER_SIZE_RE = re.compile(r"([\d.]+)\s*([A-Za-z]+)")
_DOCKER_UNITS = {
    "b": 1,
    "kb": 1000,
    "kib": 1024,
    "mb": 1000**2,
    "mib": 1024**2,
    "gb": 1000**3,
    "gib": 1024**3,
    "tb": 1000**4,
    "tib": 1024**4,
}
_CONTAINER_TTL_SEC = 2.0
_container_cache: dict[str, Any] = {"at": 0.0, "rows": []}


def _gb(nbytes: int) -> float:
    return round(max(0, int(nbytes or 0)) / (1024**3), 1)


def _mb(nbytes: int) -> float:
    return round(max(0, int(nbytes or 0)) / (1024**2), 1)


def _windows_creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


def _win_dll(name: str) -> Any:
    import ctypes

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError(f"WinDLL unavailable for {name}")
    return loader(name, use_last_error=True)


def _format_rss(nbytes: int) -> str:
    try:
        from application.hermes_processes import format_rss

        return format_rss(nbytes)
    except Exception:
        n = max(0, int(nbytes or 0))
        if n >= 1024**3:
            return f"{n / 1024**3:.1f} GB"
        if n >= 1024**2:
            return f"{n / 1024**2:.0f} MB"
        return f"{n} B"


def _windows_rss(pid: int) -> int:  # pragma: no cover - Win32 RSS
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = _win_dll("kernel32")
    psapi = _win_dll("psapi")
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return 0

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return 0
        return int(counters.WorkingSetSize or 0)
    except Exception:
        return 0
    finally:
        kernel32.CloseHandle(handle)


def _posix_rss(pid: int) -> int:
    from pathlib import Path

    page = 4096
    sysconf = getattr(os, "sysconf", None)
    if callable(sysconf):
        try:
            raw_page = sysconf("SC_PAGE_SIZE")
            page = int(str(raw_page)) if raw_page is not None else 4096
        except (TypeError, ValueError, OSError):
            page = 4096
        if page <= 0:
            page = 4096
    try:
        parts = (Path("/proc") / str(pid) / "statm").read_text(encoding="utf-8", errors="replace").split()
    except OSError:
        return 0
    return int(parts[1]) * page if len(parts) > 1 else 0


def _system_memory_windows() -> dict[str, int]:  # pragma: no cover - Win32 GlobalMemoryStatusEx
    import ctypes
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    kernel32 = _win_dll("kernel32")
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {}
    total = int(status.ullTotalPhys or 0)
    avail = int(status.ullAvailPhys or 0)
    commit_total = int(status.ullTotalPageFile or 0)
    commit_avail = int(status.ullAvailPageFile or 0)
    return {
        "used": max(0, total - avail),
        "total": total,
        "available": max(0, avail),
        "committed": max(0, commit_total - commit_avail),
        "committed_total": commit_total,
        "cached": 0,
    }


def _system_memory_posix() -> dict[str, int]:
    from pathlib import Path

    values = {"MemTotal": 0, "MemAvailable": 0, "Cached": 0, "SReclaimable": 0, "SwapTotal": 0, "SwapFree": 0}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        key = line.split(":", 1)[0]
        if key in values:
            values[key] = int(line.split()[1]) * 1024
    total = values["MemTotal"]
    available = values["MemAvailable"]
    cached = values["Cached"] + values["SReclaimable"]
    return {
        "used": max(0, total - available),
        "total": total,
        "available": max(0, available),
        "committed": max(0, values["SwapTotal"] - values["SwapFree"]),
        "committed_total": values["SwapTotal"],
        "cached": cached,
    }


def _system_memory_detail() -> dict[str, Any]:
    try:
        raw = _system_memory_windows() if sys.platform == "win32" else _system_memory_posix()
    except Exception:
        _log.debug("System RAM snapshot failed", exc_info=True)
        raw = {}
    used = int(raw.get("used") or 0)
    total = int(raw.get("total") or 0)
    available = int(raw.get("available") or 0)
    committed = int(raw.get("committed") or 0)
    committed_total = int(raw.get("committed_total") or 0)
    cached = int(raw.get("cached") or 0)
    return {
        "used_bytes": used,
        "total_bytes": total,
        "available_bytes": available,
        "used_gb": _gb(used),
        "total_gb": _gb(total),
        "available_gb": _gb(available),
        "used_pct": round((100.0 * used / total), 1) if total else 0.0,
        "committed_bytes": committed,
        "committed_total_bytes": committed_total,
        "committed_gb": _gb(committed),
        "committed_total_gb": _gb(committed_total),
        "cached_bytes": cached,
        "cached_gb": _gb(cached),
    }


def _iter_process_rows() -> list[tuple[int, int, str]]:
    if sys.platform == "win32":  # pragma: no cover - Toolhelp32 snapshot
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = _win_dll("kernel32")
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            return []
        rows: list[tuple[int, int, str]] = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return []
            while True:
                rows.append(
                    (int(entry.th32ProcessID), int(entry.th32ParentProcessID), str(entry.szExeFile or ""))
                )
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
            return rows
        finally:
            kernel32.CloseHandle(snapshot)
    from pathlib import Path

    proc = Path("/proc")
    if not proc.is_dir():
        return []
    rows = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        comm_end = stat.rfind(")")
        fields = stat[comm_end + 2 :].split() if comm_end >= 0 else []
        ppid = int(fields[1]) if len(fields) > 1 else 0
        rows.append((int(entry.name), ppid, name or entry.name))
    return rows


def _iter_process_parents() -> list[tuple[int, int]]:
    return [(pid, ppid) for pid, ppid, _name in _iter_process_rows()]


def _descendant_pids(root: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, ppid in _iter_process_parents():
        children.setdefault(ppid, []).append(pid)
    out: set[int] = set()
    stack = [int(root)]
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(children.get(current) or [])
    return out


def _rss(pid: int) -> int:
    if sys.platform == "win32":  # pragma: no cover - Win32 RSS
        return _windows_rss(pid)
    return _posix_rss(pid)


def _parse_docker_size(raw: str) -> int:
    text = str(raw or "").split("/", 1)[0].strip()
    match = _DOCKER_SIZE_RE.match(text)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).lower()
    return int(value * _DOCKER_UNITS.get(unit, 1))


def _parse_docker_mem(raw: str) -> tuple[int, int]:
    text = str(raw or "")
    left, sep, right = text.partition("/")
    used = _parse_docker_size(left)
    limit = _parse_docker_size(right) if sep else 0
    return used, limit


def _parse_pct(raw: str) -> float | None:
    text = str(raw or "").replace("%", "").strip()
    if not text:
        return None
    try:
        return round(float(text), 1)
    except ValueError:
        return None


def _docker_run(args: list[str], *, timeout: float) -> str:
    try:
        from docker_manager.manager import _docker_executable
    except Exception:
        return ""
    exe = _docker_executable()
    kwargs: dict[str, Any] = {
        "args": [exe, *args],
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
    }
    if sys.platform == "win32":  # pragma: no cover - hidden console
        kwargs["creationflags"] = _windows_creation_flags()
    try:
        completed = subprocess.run(**kwargs)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return ""
    if int(completed.returncode) != 0:
        return ""
    return str(completed.stdout or "")


def _managed_container_rows(*, use_cache: bool = True) -> list[dict[str, Any]]:
    now = time.monotonic()
    if use_cache and (now - float(_container_cache.get("at") or 0)) < _CONTAINER_TTL_SEC:
        return list(_container_cache.get("rows") or [])
    from docker_manager.manager import MANAGED_LABEL

    known = ("qdrant", "open-webui", "ollama", "searxng", "comfy", "chiron")
    listing = _docker_run(["ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Labels}}"], timeout=4.0)
    wanted: list[tuple[str, str]] = []
    for line in listing.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        container_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ""
        labels = parts[2] if len(parts) > 2 else ""
        if not container_id:
            continue
        if f"{MANAGED_LABEL}=true" in labels or any(token in name.lower() for token in known):
            wanted.append((container_id, name))
    rows: list[dict[str, Any]] = []
    if wanted:
        ids = [item[0] for item in wanted]
        raw = _docker_run(
            ["stats", "--no-stream", "--format", "{{.ID}}\t{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}", *ids],
            timeout=6.0,
        )
        by_id = {cid: name for cid, name in wanted}
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            cid = parts[0].strip()
            name = parts[1].strip() or next((by_id[key] for key in by_id if cid.startswith(key) or key.startswith(cid)), cid)
            used, limit = _parse_docker_mem(parts[2])
            cpu_pct = _parse_pct(parts[3] if len(parts) > 3 else "")
            rows.append(
                {
                    "id": f"container:{cid}",
                    "kind": "container",
                    "name": name or cid,
                    "pid": None,
                    "rss_bytes": used,
                    "rss": _format_rss(used),
                    "limit_bytes": limit,
                    "cpu_pct": cpu_pct,
                    "detail": "Docker",
                }
            )
    _container_cache["at"] = now
    _container_cache["rows"] = rows
    return list(rows)


def _managed_container_rss() -> int:
    return sum(int(row.get("rss_bytes") or 0) for row in _managed_container_rows())


def _hermes_rss(host_pids: set[int]) -> int:
    try:
        from application.hermes_processes import collect_managed_processes
    except Exception:
        return 0
    total = 0
    try:
        for proc in collect_managed_processes():
            pid = proc.get("pid")
            if not proc.get("alive"):
                continue
            if pid is not None and int(pid) in host_pids:
                continue
            total += int(proc.get("rss_bytes") or 0)
    except Exception:
        _log.debug("Hermes RAM snapshot failed", exc_info=True)
    return total


def _script_from_cmdline(cmdline: str) -> str:
    text = " ".join(str(cmdline or "").replace('"', " ").split())
    if not text:
        return ""
    parts = text.split()
    if "-m" in parts:
        index = parts.index("-m")
        if index + 1 < len(parts):
            return parts[index + 1]
    for part in reversed(parts):
        lower = part.lower().replace("\\", "/")
        if lower.endswith(".py"):
            return part.rsplit("/", 1)[-1]
    return ""


def _process_detail(pid: int, exe_name: str, self_pid: int) -> str:
    if pid == self_pid:
        return "WebUI backend"
    try:
        from application.hermes_processes import read_process_cmdline

        snippet = _script_from_cmdline(read_process_cmdline(pid))
    except Exception:
        snippet = ""
    if snippet:
        return snippet
    return "Host"


def _host_process_rows(host_pids: set[int], names: dict[int, str]) -> list[dict[str, Any]]:
    self_pid = os.getpid()
    hermes_by_pid: dict[int, dict[str, Any]] = {}
    try:
        from application.hermes_processes import collect_managed_processes

        for proc in collect_managed_processes():
            pid = proc.get("pid")
            if pid is None or not proc.get("alive"):
                continue
            hermes_by_pid[int(pid)] = proc
    except Exception:
        _log.debug("Hermes process labels failed", exc_info=True)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for pid in sorted(host_pids):
        rss = _rss(pid)
        if rss <= 0 and pid != self_pid:
            continue
        hermes = hermes_by_pid.get(pid)
        kind = "hermes" if hermes else "process"
        label = str((hermes or {}).get("label") or "")
        exe_name = names.get(pid) or f"pid {pid}"
        name = f"Hermes {label}".strip() if hermes else exe_name
        detail = f"Hermes {label}".strip() if hermes else _process_detail(pid, exe_name, self_pid)
        rows.append(
            {
                "id": f"proc:{pid}",
                "kind": kind,
                "name": name,
                "pid": pid,
                "rss_bytes": rss,
                "rss": _format_rss(rss),
                "cpu_pct": None,
                "detail": detail,
            }
        )
        seen.add(pid)
    for pid, proc in hermes_by_pid.items():
        if pid in seen:
            continue
        rss = int(proc.get("rss_bytes") or 0)
        rows.append(
            {
                "id": f"hermes:{proc.get('id') or pid}",
                "kind": "hermes",
                "name": f"Hermes {proc.get('label') or pid}",
                "pid": pid,
                "rss_bytes": rss,
                "rss": str(proc.get("rss") or _format_rss(rss)),
                "cpu_pct": None,
                "detail": "Hermes",
            }
        )
    return rows


def _gpu_snapshot() -> dict[str, Any] | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    kwargs: dict[str, Any] = {
        "args": [
            nvidia_smi,
            "--query-gpu=name,driver_version,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        "capture_output": True,
        "text": True,
        "timeout": 2,
        "check": False,
    }
    if sys.platform == "win32":  # pragma: no cover - hidden console
        kwargs["creationflags"] = _windows_creation_flags()
    try:
        result = subprocess.run(**kwargs)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout or not result.stdout.strip():
        return None
    line = result.stdout.strip().split("\n")[0].strip()
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 6:
        return None

    def _int_or_none(raw: str) -> int | None:
        text = (raw or "").replace("%", "").replace("MiB", "").replace("MB", "").replace("C", "").strip()
        return int(text) if text.isdigit() else None

    return {
        "name": parts[0] or "GPU",
        "driver_version": parts[1] or "",
        "utilization_pct": _int_or_none(parts[2]),
        "memory_used_mb": _int_or_none(parts[3]),
        "memory_total_mb": _int_or_none(parts[4]),
        "temperature_c": _int_or_none(parts[5]),
    }


def collect_gpu_snapshot() -> dict[str, Any] | None:
    """Return the first NVIDIA GPU telemetry slice, or None when nvidia-smi is unavailable."""
    try:
        return _gpu_snapshot()
    except Exception:
        _log.debug("GPU snapshot failed", exc_info=True)
        return None


def collect_ram_metrics() -> dict[str, Any]:
    """System RAM plus ChironAI host tree, Hermes, and managed Docker containers."""
    memory = _system_memory_detail()
    used = int(memory.get("used_bytes") or 0)
    total = int(memory.get("total_bytes") or 0)
    host_pids = _descendant_pids(os.getpid())
    host_bytes = sum(_rss(pid) for pid in host_pids)
    host_bytes += _hermes_rss(host_pids)
    try:
        container_bytes = _managed_container_rss()
    except Exception:
        _log.debug("Docker RAM snapshot failed", exc_info=True)
        container_bytes = 0
    app_bytes = host_bytes + container_bytes
    return {
        "system_used_bytes": used,
        "system_total_bytes": total,
        "system_used_gb": _gb(used),
        "system_total_gb": _gb(total),
        "app_host_bytes": host_bytes,
        "app_containers_bytes": container_bytes,
        "app_bytes": app_bytes,
        "app_gb": _gb(app_bytes),
    }


def collect_performance_snapshot() -> dict[str, Any]:
    """Live Task Manager-style snapshot: memory, GPU, host processes, and containers."""
    memory = _system_memory_detail()
    names = {pid: name for pid, _ppid, name in _iter_process_rows()}
    host_pids = _descendant_pids(os.getpid())
    process_rows = _host_process_rows(host_pids, names)
    try:
        from application.host_cpu import sample_cpu_pct

        cpu_by_pid = sample_cpu_pct(
            [int(row["pid"]) for row in process_rows if row.get("pid") is not None]
        )
        for row in process_rows:
            pid = row.get("pid")
            if pid is None:
                continue
            row["cpu_pct"] = cpu_by_pid.get(int(pid))
    except Exception:
        _log.debug("Host CPU snapshot failed", exc_info=True)
    host_bytes = sum(int(row.get("rss_bytes") or 0) for row in process_rows)
    try:
        container_rows = _managed_container_rows()
    except Exception:
        _log.debug("Docker RAM snapshot failed", exc_info=True)
        container_rows = []
    container_bytes = sum(int(row.get("rss_bytes") or 0) for row in container_rows)
    app_bytes = host_bytes + container_bytes
    processes = sorted([*process_rows, *container_rows], key=lambda row: int(row.get("rss_bytes") or 0), reverse=True)
    gpu = collect_gpu_snapshot()
    return {
        "captured_at_ms": int(time.time() * 1000),
        "memory": memory,
        "app": {
            "host_bytes": host_bytes,
            "containers_bytes": container_bytes,
            "bytes": app_bytes,
            "host_gb": _gb(host_bytes),
            "containers_gb": _gb(container_bytes),
            "gb": _gb(app_bytes),
            "host_mb": _mb(host_bytes),
            "containers_mb": _mb(container_bytes),
        },
        "gpu": gpu,
        "processes": processes,
    }
