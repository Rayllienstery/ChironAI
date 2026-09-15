"""OS snapshot of host Hermes gateway and dashboard process trees."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

_log = logging.getLogger("chironai.hermes")

DEFAULT_API_PORT = 8642
DEFAULT_DASHBOARD_PORT = 9119


def format_rss(nbytes: int) -> str:
    n = max(0, int(nbytes or 0))
    if n >= 1024**3:
        value = n / 1024**3
        return f"{value:.1f} GB" if value < 10 else f"{value:.0f} GB"
    if n >= 1024**2:
        value = n / 1024**2
        return f"{value:.0f} MB" if value >= 10 else f"{value:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def empty_managed_processes() -> list[dict[str, Any]]:
    return [
        {"id": "gateway", "label": "Gateway", "alive": False, "pid": None, "rss_bytes": 0, "rss": ""},
        {"id": "dashboard", "label": "Dashboard", "alive": False, "pid": None, "rss_bytes": 0, "rss": ""},
    ]


def _win_dll(name: str) -> Any:
    import ctypes

    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError(f"WinDLL unavailable for {name}")
    return loader(name, use_last_error=True)


def _role_for_cmdline(cmdline: str) -> str | None:
    text = " ".join(str(cmdline or "").lower().replace("/", "\\").split())
    if "hermes" not in text:
        return None
    if "dashboard" in text:
        return "dashboard"
    if "gateway run" in text:
        return "gateway"
    return None


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


def _windows_cmdline(pid: int) -> str:  # pragma: no cover - NtQueryInformationProcess
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ProcessCommandLineInformation = 60
    kernel32 = _win_dll("kernel32")
    ntdll = _win_dll("ntdll")
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        length = wintypes.ULONG(0)
        ntdll.NtQueryInformationProcess(
            handle, ProcessCommandLineInformation, None, 0, ctypes.byref(length)
        )
        if not length.value:
            return ""
        buf = ctypes.create_string_buffer(length.value)
        status = ntdll.NtQueryInformationProcess(
            handle, ProcessCommandLineInformation, buf, length, ctypes.byref(length)
        )
        if status != 0:
            return ""

        class UNICODE_STRING(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("MaximumLength", wintypes.USHORT),
                ("Buffer", ctypes.c_void_p),
            ]

        header = UNICODE_STRING.from_buffer_copy(buf.raw[: ctypes.sizeof(UNICODE_STRING)])
        if not header.Buffer or not header.Length:
            return ""
        return ctypes.wstring_at(header.Buffer, header.Length // 2)
    except Exception:
        return ""
    finally:
        kernel32.CloseHandle(handle)


def read_process_cmdline(pid: int) -> str:
    """Best-effort command line for a live process."""
    if sys.platform == "win32":  # pragma: no cover - Win32 command line
        return _windows_cmdline(pid)
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def _windows_listener_pids() -> dict[int, int]:  # pragma: no cover - iphlpapi listeners
    import ctypes
    import socket
    from ctypes import wintypes

    class MIB_TCPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwState", wintypes.DWORD),
            ("dwLocalAddr", wintypes.DWORD),
            ("dwLocalPort", wintypes.DWORD),
            ("dwRemoteAddr", wintypes.DWORD),
            ("dwRemotePort", wintypes.DWORD),
            ("dwOwningPid", wintypes.DWORD),
        ]

    AF_INET = 2
    TCP_TABLE_OWNER_PID_ALL = 5
    MIB_TCP_STATE_LISTEN = 2
    iphlpapi = _win_dll("iphlpapi")
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    if not size.value:
        return {}
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), True, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0):
        return {}
    count = wintypes.DWORD.from_buffer_copy(buf.raw[:4]).value
    offset = 4
    row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
    listeners: dict[int, int] = {}
    for _ in range(int(count)):
        row = MIB_TCPROW_OWNER_PID.from_buffer_copy(buf.raw[offset : offset + row_size])
        offset += row_size
        if int(row.dwState) != MIB_TCP_STATE_LISTEN:
            continue
        port = int(socket.ntohs(row.dwLocalPort & 0xFFFF))
        listeners[port] = int(row.dwOwningPid)
    return listeners


def _iter_windows_processes() -> list[dict[str, Any]]:  # pragma: no cover - Toolhelp32 snapshot
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
    rows: list[dict[str, Any]] = []
    interesting = {"hermes.exe", "hermes", "python.exe", "pythonw.exe", "python"}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            name = str(entry.szExeFile or "")
            pid = int(entry.th32ProcessID)
            if name.lower() in interesting:
                rows.append(
                    {
                        "pid": pid,
                        "ppid": int(entry.th32ParentProcessID),
                        "name": name,
                        "rss": _windows_rss(pid),
                        "cmdline": _windows_cmdline(pid),
                    }
                )
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return rows
    finally:
        kernel32.CloseHandle(snapshot)


def _iter_posix_processes() -> list[dict[str, Any]]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
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
    rows: list[dict[str, Any]] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            statm = (entry / "statm").read_text(encoding="utf-8", errors="replace").split()
        except OSError:
            continue
        if "hermes" not in cmdline.lower():
            continue
        comm_start = stat.find("(")
        comm_end = stat.rfind(")")
        name = stat[comm_start + 1 : comm_end] if comm_start >= 0 and comm_end > comm_start else entry.name
        fields = stat[comm_end + 2 :].split()
        ppid = int(fields[1]) if len(fields) > 1 else 0
        rss = int(statm[1]) * page if len(statm) > 1 else 0
        rows.append(
            {
                "pid": int(entry.name),
                "ppid": ppid,
                "name": name,
                "rss": rss,
                "cmdline": cmdline,
            }
        )
    return rows


def _tree_for_pid(pid: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pid = {int(row["pid"]): row for row in rows}
    children: dict[int, list[int]] = {}
    for row in rows:
        children.setdefault(int(row.get("ppid") or 0), []).append(int(row["pid"]))
    root = pid
    seen: set[int] = set()
    current = pid
    while current and current not in seen:
        seen.add(current)
        row = by_pid.get(current)
        if row is None:
            break
        if str(row.get("name") or "").lower().startswith("hermes"):
            root = current
            break
        current = int(row.get("ppid") or 0)
    out: list[dict[str, Any]] = []
    stack = [root]
    visited: set[int] = set()
    while stack:
        item = stack.pop()
        if item in visited:
            continue
        visited.add(item)
        row = by_pid.get(item)
        if row is not None:
            out.append(row)
        stack.extend(children.get(item) or [])
    return out


def collect_managed_processes(
    *,
    api_port: int = DEFAULT_API_PORT,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
) -> list[dict[str, Any]]:
    """OS snapshot of the host Hermes gateway and dashboard process trees."""
    try:
        if sys.platform == "win32":  # pragma: no cover - Win32 snapshot
            rows = _iter_windows_processes()
        else:
            rows = _iter_posix_processes()
    except Exception:
        _log.debug("Hermes process snapshot failed", exc_info=True)
        return empty_managed_processes()
    grouped: dict[str, list[dict[str, Any]]] = {"gateway": [], "dashboard": []}
    for row in rows:
        role = _role_for_cmdline(str(row.get("cmdline") or ""))
        if role:
            grouped[role].append(row)
    if sys.platform == "win32":  # pragma: no cover - listener fallback
        try:
            listeners = _windows_listener_pids()
        except Exception:
            listeners = {}
        for role_id, port in (("gateway", int(api_port)), ("dashboard", int(dashboard_port))):
            if grouped[role_id]:
                continue
            listener_pid = listeners.get(port)
            if listener_pid:
                grouped[role_id] = _tree_for_pid(int(listener_pid), rows) or [
                    {
                        "pid": int(listener_pid),
                        "ppid": 0,
                        "name": "",
                        "rss": _windows_rss(int(listener_pid)),
                        "cmdline": "",
                    }
                ]
    out: list[dict[str, Any]] = []
    for role_id, label in (("gateway", "Gateway"), ("dashboard", "Dashboard")):
        members = grouped[role_id]
        rss = sum(int(item.get("rss") or 0) for item in members)
        alive = bool(members)
        display_pid = None
        for item in members:
            if str(item.get("name") or "").lower().startswith("hermes"):
                display_pid = int(item["pid"])
                break
        if display_pid is None and members:
            display_pid = int(members[0]["pid"])
        out.append(
            {
                "id": role_id,
                "label": label,
                "alive": alive,
                "pid": display_pid,
                "rss_bytes": rss,
                "rss": format_rss(rss) if alive else "",
            }
        )
    return out
