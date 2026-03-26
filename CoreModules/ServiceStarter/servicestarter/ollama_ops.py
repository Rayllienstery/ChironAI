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


def stop_ollama_process() -> tuple[bool, str]:
    try:
        if sys.platform == "win32":
            proc = subprocess.run(
                ["taskkill", "/IM", "ollama.exe", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        else:
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


def ollama_port_from_base_url(base_url: str) -> int:
    from urllib.parse import urlparse

    u = base_url if "://" in base_url else f"http://{base_url}"
    p = urlparse(u)
    return int(p.port or 11343)
