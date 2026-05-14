"""Standalone runtime helpers for rag_service dependencies.

Owns start/stop/status logic for the services that rag_service needs at runtime:
- Ollama
- Qdrant
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from docker_manager import DockerContainerSpec, DockerManager
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


def _ollama_container_name() -> str:
    return (os.getenv("OLLAMA_CONTAINER_NAME") or "chironai-ollama").strip() or "chironai-ollama"


def _ollama_docker_image() -> str:
    return (os.getenv("OLLAMA_DOCKER_IMAGE") or "ollama/ollama:latest").strip() or "ollama/ollama:latest"


def _ollama_docker_volume() -> str:
    return (os.getenv("OLLAMA_DOCKER_VOLUME") or "ollama_models:/root/.ollama").strip()


def ensure_ollama_container(cfg: RagRuntimeConfig) -> tuple[bool, str]:
    """Start Ollama as a Docker container (Docker-first, no native binary)."""
    parsed = urlparse(cfg.ollama_base_url if "://" in cfg.ollama_base_url else f"http://{cfg.ollama_base_url}")
    host_port = int(parsed.port or 11434)
    volume = _ollama_docker_volume()
    spec = DockerContainerSpec(
        name=_ollama_container_name(),
        image=_ollama_docker_image(),
        ports=[f"{host_port}:11434"],
        env={"OLLAMA_HOST": "0.0.0.0:11434"},
        volumes=[volume] if volume else [],
        restart="unless-stopped",
        labels={"chironai.service": "ollama"},
    )
    result = _docker_manager().ensure_container(spec)
    ok = bool(result.get("ok"))
    msg = str(result.get("message") or result.get("details") or result.get("error") or "")
    return ok, msg or ("started" if ok else "failed")


def ollama_port_from_base_url(base_url: str, default_port: int = 11434) -> int:
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    return int(parsed.port or default_port)


def _docker_manager() -> DockerManager:
    return DockerManager()


def docker_version_available() -> bool:
    return bool(_docker_manager().status().get("cli_available"))


def docker_engine_info() -> tuple[bool, str]:
    return _docker_manager().engine_info()


def docker_engine_ready() -> bool:
    ok, _ = docker_engine_info()
    return ok


def wait_for_docker_engine(cfg: RagRuntimeConfig, *, start_desktop_on_windows: bool = True) -> tuple[bool, str]:
    return _docker_manager().wait_engine_tuple(
        docker_desktop_exe=cfg.docker_desktop_exe,
        timeout=cfg.docker_ready_timeout_sec,
        interval=cfg.docker_poll_interval_sec,
        start_desktop_on_windows=start_desktop_on_windows,
    )


def container_exists(name: str) -> bool:
    return _docker_manager().container_exists(name)


def container_is_running(name: str) -> bool:
    return _docker_manager().container_running(name)


def docker_pull(image: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    result = _docker_manager().pull_image(image)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def docker_start_container(name: str) -> tuple[bool, str]:
    result = _docker_manager().start_container(name)
    msg = str(result.get("message") or result.get("details") or result.get("error") or "")
    if not bool(result.get("ok")) and "already running" in msg.lower():
        return True, "already running"
    return bool(result.get("ok")), msg


def docker_stop_container(name: str) -> tuple[bool, str]:
    result = _docker_manager().stop_container(name)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


def ensure_qdrant_container(cfg: RagRuntimeConfig) -> tuple[bool, str]:
    spec = DockerContainerSpec(
        name=cfg.qdrant_container_name,
        image=cfg.qdrant_image,
        ports=[
            f"{cfg.qdrant_host_http_port}:6333",
            f"{cfg.qdrant_host_grpc_port}:6334",
        ],
        volumes=["qdrant_storage:/qdrant/storage"],
        restart="unless-stopped",
        labels={"chironai.service": "qdrant"},
    )
    result = _docker_manager().ensure_container(spec)
    return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")


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
        # If the Docker container is already running, the port is already served correctly.
        if _docker_manager().container_running(_ollama_container_name()):
            return True, "already running (container)"
        # Port may respond from a native Ollama process — stop it first to free the port.
        if ollama_ping(self._cfg.ollama_base_url, timeout=2.0).get("ok"):
            stop_ollama_process()
        return ensure_ollama_container(self._cfg)

    def stop_ollama(self) -> tuple[bool, str]:
        return docker_stop_container(_ollama_container_name())

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
