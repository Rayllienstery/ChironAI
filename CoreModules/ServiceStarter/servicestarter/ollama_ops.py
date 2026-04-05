"""Ollama CLI and HTTP reachability."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any

import requests

from servicestarter.config import ServiceStarterConfig


def find_ollama_executable() -> str | None:
    return shutil.which("ollama")


def ollama_ping(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    base = base_url.rstrip("/")
    url = f"{base}/api/tags"
    result: dict[str, Any] = {"ok": False, "url": base}
    try:
        r = requests.get(url, timeout=timeout)
        result["status_code"] = r.status_code
        result["ok"] = r.ok
        return result
    except requests.RequestException as e:
        result["error"] = str(e)
        return result


def start_ollama_serve(cfg: ServiceStarterConfig) -> tuple[bool, str]:
    exe = find_ollama_executable()
    if not exe:
        return False, "ollama executable not found in PATH"
    env = dict(os.environ)
    env["OLLAMA_HOST"] = cfg.ollama_listen
    kwargs: dict[str, Any] = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([exe, "serve"], **kwargs)
        return True, "ollama serve started"
    except OSError as e:
        return False, str(e)


def _win_pids_listening_on_tcp_port(port: int) -> list[int]:
    """PIDs with TCP LISTENING on local port (Windows ``netstat -ano``)."""
    proc = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    pids: set[int] = set()
    port_token = f":{int(port)}"
    for line in proc.stdout.splitlines():
        line_st = line.strip()
        if not line_st.upper().startswith("TCP"):
            continue
        if "LISTENING" not in line_st.upper():
            continue
        if port_token not in line_st:
            continue
        parts = line_st.split()
        if not parts:
            continue
        last = parts[-1]
        if last.isdigit():
            pid = int(last)
            if pid > 0:
                pids.add(pid)
    return sorted(pids)


def _win_pid_image_mentions_ollama(pid: int) -> bool:
    """True if ``tasklist`` CSV line for PID suggests an Ollama process."""
    proc = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    return "ollama" in (proc.stdout or "").lower()


def _win_taskkill_not_found_ok(proc: subprocess.CompletedProcess[str]) -> bool:
    if proc.returncode == 0:
        return True
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
    if proc.returncode == 128 and ("not found" in combined or "not running" in combined):
        return True
    return False


def stop_ollama_process(listen_port: int | None = None) -> tuple[bool, str]:
    """Stop Ollama.

    On Windows: if ``listen_port`` is set (e.g. 11434), ``taskkill /PID`` listeners on that port,
    then ``taskkill /IM ollama.exe`` (handles cases where only ``taskkill /IM`` failed before).
    """
    try:
        if sys.platform == "win32":
            messages: list[str] = []
            if listen_port is not None:
                for pid in _win_pids_listening_on_tcp_port(listen_port):
                    if not _win_pid_image_mentions_ollama(pid):
                        messages.append(
                            f"skip PID {pid} on port {listen_port} (tasklist does not look like ollama)"
                        )
                        continue
                    proc = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30,
                    )
                    txt = (proc.stdout or proc.stderr or "").strip()
                    if txt:
                        messages.append(txt)

            proc = subprocess.run(
                ["taskkill", "/IM", "ollama.exe", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            txt = (proc.stdout or proc.stderr or "").strip()
            if txt:
                messages.append(txt)

            if listen_port is not None:
                remaining = _win_pids_listening_on_tcp_port(listen_port)
                ok = len(remaining) == 0
                if not ok:
                    messages.append(f"port {listen_port} still has listener PID(s): {remaining}")
                return ok, "; ".join(messages) if messages else ("ok" if ok else "failed")

            ok = proc.returncode == 0 or _win_taskkill_not_found_ok(proc)
            return ok, txt or ("ok" if ok else "taskkill failed")

        proc = subprocess.run(
            ["pkill", "-f", "ollama"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        ok = proc.returncode == 0
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return ok, out or ("ok" if ok else "failed")
    except Exception as e:
        return False, str(e)


def ollama_port_from_base_url(base_url: str, default_port: int = 11343) -> int:
    from urllib.parse import urlparse

    u = base_url if "://" in base_url else f"http://{base_url}"
    p = urlparse(u)
    return int(p.port or default_port)
