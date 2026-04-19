"""Standalone runtime helpers for rag_service dependencies.

Owns start/stop/status logic for the services that rag_service needs at runtime:
- Ollama
- Qdrant
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from rag_service.config import get_ollama_chat_url, get_qdrant_url


def _ollama_base_url_from_chat_url(chat_url: str) -> str:
    chat = (chat_url or "").rstrip("/")
    if chat.endswith("/api/chat"):
        return chat[: -len("/api/chat")]
    return chat


def _ollama_listen_from_base(base_url: str, default_host: str) -> str:
    base_url = (base_url or "").rstrip("/")
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or default_host
    port = parsed.port or 11434
    return f"{host}:{port}"


@dataclass(frozen=True)
class RagRuntimeConfig:
    ollama_base_url: str
    ollama_listen: str
    qdrant_http_url: str
    qdrant_container_name: str
    qdrant_image: str
    qdrant_host_http_port: int
    qdrant_host_grpc_port: int
    docker_desktop_exe: str
    docker_ready_timeout_sec: float
    docker_poll_interval_sec: float
    http_wait_timeout_sec: float

    @classmethod
    def from_env(cls) -> RagRuntimeConfig:
        chat_url = get_ollama_chat_url()
        ollama_base = _ollama_base_url_from_chat_url(chat_url)
        parsed_ollama = urlparse(ollama_base if "://" in ollama_base else f"http://{ollama_base}")
        default_host = parsed_ollama.hostname or os.getenv("OLLAMA_LISTEN_HOST", "127.0.0.1")
        listen = os.getenv("OLLAMA_HOST_VALUE") or _ollama_listen_from_base(ollama_base, default_host)

        qdrant_url = get_qdrant_url().rstrip("/")
        parsed_qdrant = urlparse(qdrant_url if "://" in qdrant_url else f"http://{qdrant_url}")
        q_http_port = int(os.getenv("QDRANT_HOST_HTTP_PORT", str(parsed_qdrant.port or 6333)))
        q_grpc_port = int(os.getenv("QDRANT_HOST_GRPC_PORT", "6334"))
        return cls(
            ollama_base_url=ollama_base.rstrip("/"),
            ollama_listen=listen,
            qdrant_http_url=qdrant_url,
            qdrant_container_name=os.getenv("QDRANT_CONTAINER_NAME", "qdrant"),
            qdrant_image=os.getenv("QDRANT_IMAGE", "qdrant/qdrant:latest"),
            qdrant_host_http_port=q_http_port,
            qdrant_host_grpc_port=q_grpc_port,
            docker_desktop_exe=os.getenv(
                "DOCKER_DESKTOP_EXE",
                r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            ),
            docker_ready_timeout_sec=float(os.getenv("RAG_RUNTIME_DOCKER_READY_TIMEOUT", "120")),
            docker_poll_interval_sec=float(os.getenv("RAG_RUNTIME_DOCKER_POLL_INTERVAL", "5")),
            http_wait_timeout_sec=float(os.getenv("RAG_RUNTIME_HTTP_WAIT_TIMEOUT", "60")),
        )


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


def start_ollama_serve(cfg: RagRuntimeConfig) -> tuple[bool, str]:
    exe = find_ollama_executable()
    if not exe:
        return False, "ollama executable not found in PATH"
    env = dict(os.environ)
    env["OLLAMA_HOST"] = cfg.ollama_listen
    kwargs: dict[str, Any] = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([exe, "serve"], **kwargs)
        return True, "ollama serve started"
    except OSError as e:
        return False, str(e)


def ollama_port_from_base_url(base_url: str, default_port: int = 11434) -> int:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    return int(parsed.port or default_port)


def _resolved_docker_executable() -> str:
    env = (os.getenv("DOCKER_EXE") or "").strip()
    if env:
        return env
    found = shutil.which("docker")
    if found:
        return found
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = os.path.join(pf, "Docker", "Docker", "resources", "bin", "docker.exe")
        if os.path.isfile(candidate):
            return candidate
    return "docker"


def run_docker(args: list[str], *, timeout: float | None = 300.0) -> tuple[int, str, str]:
    exe = _resolved_docker_executable()
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return 127, "", f"Docker CLI not found or not executable: {exe!r}"
    except PermissionError as e:
        return 126, "", f"Docker CLI permission denied: {exe!r}: {e}"
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def docker_version_available() -> bool:
    code, _, _ = run_docker(["--version"], timeout=10.0)
    return code == 0


def docker_engine_info() -> tuple[bool, str]:
    code, out, err = run_docker(["info"], timeout=15.0)
    if code == 0:
        return True, ""
    return False, (err or out or "").strip()


def docker_engine_ready() -> bool:
    ok, _ = docker_engine_info()
    return ok


def wait_for_docker_engine(cfg: RagRuntimeConfig, *, start_desktop_on_windows: bool = True) -> tuple[bool, str]:
    ready, last_detail = docker_engine_info()
    if ready:
        return True, "docker engine ready"
    if start_desktop_on_windows and sys.platform == "win32":
        try:
            subprocess.Popen([cfg.docker_desktop_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            return False, f"failed to start Docker Desktop: {e}"
    deadline = time.monotonic() + cfg.docker_ready_timeout_sec
    last_err = "docker not ready"
    while time.monotonic() < deadline:
        ready, last_detail = docker_engine_info()
        if ready:
            return True, "docker engine became ready"
        time.sleep(cfg.docker_poll_interval_sec)
        last_err = "timeout waiting for docker info"
        if last_detail:
            last_err = f"{last_err}: {last_detail}"
    return False, last_err


def container_exists(name: str) -> bool:
    code, _, _ = run_docker(["inspect", name], timeout=15.0)
    return code == 0


def container_is_running(name: str) -> bool:
    code, out, _ = run_docker(["inspect", "-f", "{{.State.Running}}", name], timeout=15.0)
    return code == 0 and (out or "").strip().lower() == "true"


def docker_pull(image: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    code, out, err = run_docker(["pull", image], timeout=timeout)
    if code != 0:
        return False, err or out or f"docker pull failed ({code})"
    return True, out or "ok"


def docker_start_container(name: str) -> tuple[bool, str]:
    code, out, err = run_docker(["start", name], timeout=60.0)
    if code == 0:
        return True, (out or err or "ok").strip() or "ok"
    combined = f"{err}\n{out}".lower()
    if "already running" in combined or "is already running" in combined:
        return True, "already running"
    return False, (err or out or f"exit {code}").strip()


def docker_stop_container(name: str) -> tuple[bool, str]:
    code, out, err = run_docker(["stop", name], timeout=120.0)
    ok = code == 0
    return ok, out or err or ("ok" if ok else f"exit {code}")


def _sync_restart_policy_unless_stopped(name: str) -> None:
    run_docker(["update", "--restart", "unless-stopped", name], timeout=30.0)


def ensure_qdrant_container(cfg: RagRuntimeConfig) -> tuple[bool, str]:
    name = cfg.qdrant_container_name
    if container_is_running(name):
        return True, "already running"
    if container_exists(name):
        ok_s, msg_s = docker_start_container(name)
        if ok_s:
            _sync_restart_policy_unless_stopped(name)
        return ok_s, msg_s
    ok_pull, msg_pull = docker_pull(cfg.qdrant_image)
    if not ok_pull:
        return False, msg_pull
    code, out, err = run_docker(
        [
            "run",
            "-d",
            "-p",
            f"{cfg.qdrant_host_http_port}:6333",
            "-p",
            f"{cfg.qdrant_host_grpc_port}:6334",
            "--name",
            name,
            "-v",
            "qdrant_storage:/qdrant/storage",
            "--restart",
            "unless-stopped",
            cfg.qdrant_image,
        ],
        timeout=120.0,
    )
    if code != 0:
        return False, err or out or f"docker run failed ({code})"
    return True, out or "created"


def wait_for_http_json(
    url: str,
    *,
    path: str,
    ok_status: tuple[int, ...] = (200,),
    timeout_sec: float = 60.0,
    interval: float = 2.0,
) -> tuple[bool, str | None]:
    deadline = time.monotonic() + timeout_sec
    last_err: str | None = None
    base = url.rstrip("/")
    full = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    while time.monotonic() < deadline:
        try:
            r = requests.get(full, timeout=3)
            if r.status_code in ok_status:
                return True, None
            last_err = f"http {r.status_code}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(interval)
    return False, last_err or "timeout"


def qdrant_port_from_url(url: str) -> int:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return int(parsed.port or 6333)


class RagRuntime:
    """Owns start/stop/status for services required by rag_service."""

    def __init__(self, config: RagRuntimeConfig | None = None) -> None:
        self._cfg = config or RagRuntimeConfig.from_env()

    @property
    def cfg(self) -> RagRuntimeConfig:
        return self._cfg

    def health(self) -> dict[str, Any]:
        cfg = self._cfg
        ollama = ollama_ping(cfg.ollama_base_url, timeout=3.0)
        docker_cli = False
        docker_engine = False
        docker_err: str | None = None
        try:
            docker_cli = docker_version_available()
            docker_engine = docker_engine_ready() if docker_cli else False
        except Exception as e:
            docker_err = str(e)

        q_running_http = False
        q_http_status: int | None = None
        q_err: str | None = None
        try:
            r = requests.get(f"{cfg.qdrant_http_url.rstrip('/')}/collections", timeout=3)
            q_running_http = r.ok
            q_http_status = r.status_code
        except requests.RequestException as e:
            q_err = str(e)

        q_container = False
        try:
            q_container = container_is_running(cfg.qdrant_container_name)
        except Exception:
            pass

        return {
            "ollama": {
                "running": bool(ollama.get("ok")),
                "port": ollama_port_from_base_url(cfg.ollama_base_url),
                "url": cfg.ollama_base_url,
                "http_status": ollama.get("status_code"),
                "error": ollama.get("error"),
            },
            "docker": {
                "cli_available": docker_cli,
                "engine_available": docker_engine,
                "error": docker_err,
            },
            "qdrant": {
                "running": q_running_http,
                "container_running": q_container,
                "port": qdrant_port_from_url(cfg.qdrant_http_url),
                "url": cfg.qdrant_http_url,
                "container": cfg.qdrant_container_name,
                "http_status": q_http_status,
                "error": q_err,
            },
        }

    def start_ollama(self) -> tuple[bool, str]:
        ping = ollama_ping(self._cfg.ollama_base_url, timeout=2.0)
        if ping.get("ok"):
            return True, "already running"
        return start_ollama_serve(self._cfg)

    def stop_ollama(self) -> tuple[bool, str]:
        port = ollama_port_from_base_url(self._cfg.ollama_base_url)
        return stop_ollama_process(listen_port=port)

    def start_qdrant(self) -> tuple[bool, str]:
        ok_d, msg_d = wait_for_docker_engine(self._cfg, start_desktop_on_windows=(sys.platform == "win32"))
        if not ok_d:
            return False, f"docker: {msg_d}"
        ok, msg = ensure_qdrant_container(self._cfg)
        if ok:
            wait_for_http_json(
                self._cfg.qdrant_http_url,
                path="/collections",
                timeout_sec=self._cfg.http_wait_timeout_sec,
            )
        return ok, msg

    def stop_qdrant(self) -> tuple[bool, str]:
        return docker_stop_container(self._cfg.qdrant_container_name)

    def start_dependencies(self, services: list[str]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name in services:
            n = name.strip().lower()
            if n == "ollama":
                results["ollama"] = self.start_ollama()
            elif n == "qdrant":
                results["qdrant"] = self.start_qdrant()
            elif n == "docker":
                results["docker"] = wait_for_docker_engine(
                    self._cfg, start_desktop_on_windows=(sys.platform == "win32")
                )
            else:
                results[n] = (False, f"unknown service: {name}")
        results["health"] = self.health()
        return results


def _win_pids_listening_on_tcp_port(port: int) -> list[int]:
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
        last = parts[-1] if parts else ""
        if last.isdigit():
            pid = int(last)
            if pid > 0:
                pids.add(pid)
    return sorted(pids)


def _win_pid_image_mentions_ollama(pid: int) -> bool:
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
    return proc.returncode == 128 and ("not found" in combined or "not running" in combined)


def stop_ollama_process(listen_port: int | None = None) -> tuple[bool, str]:
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
