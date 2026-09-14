"""Per-process CPU percent from consecutive time samples."""

from __future__ import annotations

import os
import sys
import time

_cpu_cache: dict[int, tuple[float, float]] = {}
_NCPU = max(1, int(os.cpu_count() or 1))


def _filetime_seconds(low: int, high: int) -> float:
    return ((int(high) << 32) | int(low)) / 10_000_000.0


def _cpu_seconds(pid: int) -> float | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        try:
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(FILETIME),
                ctypes.POINTER(FILETIME),
                ctypes.POINTER(FILETIME),
                ctypes.POINTER(FILETIME),
            ]
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            return _filetime_seconds(kernel.dwLowDateTime, kernel.dwHighDateTime) + _filetime_seconds(
                user.dwLowDateTime, user.dwHighDateTime
            )
        except Exception:
            return None
        finally:
            kernel32.CloseHandle(handle)
    from pathlib import Path

    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    comm_end = stat.rfind(")")
    fields = stat[comm_end + 2 :].split() if comm_end >= 0 else []
    if len(fields) < 13:
        return None
    ticks = int(os.sysconf("SC_CLK_TCK") or 100)
    return (int(fields[11]) + int(fields[12])) / float(ticks)


def sample_cpu_pct(pids: list[int]) -> dict[int, float | None]:
    """Return CPU % of all cores for each pid (100% = fully busy machine)."""
    now = time.monotonic()
    wanted = {int(pid) for pid in pids if pid}
    for stale in list(_cpu_cache):
        if stale not in wanted:
            _cpu_cache.pop(stale, None)
    out: dict[int, float | None] = {}
    for pid in wanted:
        current = _cpu_seconds(pid)
        previous = _cpu_cache.get(pid)
        if current is not None:
            _cpu_cache[pid] = (now, current)
        else:
            _cpu_cache.pop(pid, None)
            out[pid] = None
            continue
        if previous is None:
            out[pid] = None
            continue
        wall = now - previous[0]
        if wall <= 0:
            out[pid] = None
            continue
        pct = 100.0 * (current - previous[1]) / wall / _NCPU
        out[pid] = round(max(0.0, min(100.0, pct)), 1)
    return out


_system_cache: tuple[float, float, float] | None = None


def _system_cpu_times() -> tuple[float, float] | None:
    """Return (idle_seconds, total_seconds) for the whole machine."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [
                ("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        kernel32.GetSystemTimes.argtypes = [
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
            ctypes.POINTER(FILETIME),
        ]
        kernel32.GetSystemTimes.restype = wintypes.BOOL
        if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        idle_sec = _filetime_seconds(idle.dwLowDateTime, idle.dwHighDateTime)
        kernel_sec = _filetime_seconds(kernel.dwLowDateTime, kernel.dwHighDateTime)
        user_sec = _filetime_seconds(user.dwLowDateTime, user.dwHighDateTime)
        return idle_sec, kernel_sec + user_sec
    from pathlib import Path

    try:
        line = Path("/proc/stat").read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    nums = [int(value) for value in parts[1:9]]
    ticks = float(os.sysconf("SC_CLK_TCK") or 100)
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return idle / ticks, sum(nums) / ticks


def sample_system_cpu_pct() -> float | None:
    """Whole-machine CPU busy percent (100% = all cores busy). First sample is None."""
    global _system_cache
    times = _system_cpu_times()
    now = time.monotonic()
    if times is None:
        return None
    idle, total = times
    previous = _system_cache
    _system_cache = (now, idle, total)
    if previous is None:
        return None
    delta_total = total - previous[2]
    delta_idle = idle - previous[1]
    if delta_total <= 0:
        return None
    pct = 100.0 * (1.0 - (delta_idle / delta_total))
    return round(max(0.0, min(100.0, pct)), 1)


__all__ = ["sample_cpu_pct", "sample_system_cpu_pct"]
