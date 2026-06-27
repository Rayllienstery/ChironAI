"""Standalone runtime helpers for rag_service dependencies.

Owns start/stop/status logic for Qdrant and Docker checks. LLM provider health is
reported via the extension-backed runtime hook when the main app has registered it.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from core.contracts.docker_runtime import DockerContainerSpec
from docker_manager import DockerManager
from rag_service.config import get_qdrant_url

DEFAULT_LLM_PROVIDER_ID = (os.getenv("DEFAULT_LLM_PROVIDER_ID") or "ollama").strip() or "ollama"


@dataclass(frozen=True)
class RagRuntimeConfig:
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
        qdrant_url = get_qdrant_url().rstrip("/")
        parsed_qdrant = urlparse(qdrant_url if "://" in qdrant_url else f"http://{qdrant_url}")
        q_http_port = int(os.getenv("QDRANT_HOST_HTTP_PORT", str(parsed_qdrant.port or 6333)))
        q_grpc_port = int(os.getenv("QDRANT_HOST_GRPC_PORT", "6334"))
        return cls(
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


def llm_provider_health_snapshot(*, provider_id: str | None = None) -> dict[str, Any]:
    """Report whether the extension-backed LLM runtime is available in this process."""
    pid = (provider_id or DEFAULT_LLM_PROVIDER_ID).strip() or DEFAULT_LLM_PROVIDER_ID
    try:
        from rag_service.infrastructure.runtime_hooks import get_llm_runtime

        runtime = get_llm_runtime()
    except Exception as exc:
        return {
            "running": False,
            "provider_id": pid,
            "error": str(exc),
        }
    if runtime is None:
        return {
            "running": False,
            "provider_id": pid,
            "error": "LLM runtime unavailable (start ChironAI or bootstrap the provider extension)",
        }
    return {
        "running": True,
        "provider_id": pid,
        "runtime_ready": True,
    }


def ollama_ping(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Deprecated: use ``llm_provider_health_snapshot`` (ignores ``base_url``)."""
    del base_url, timeout
    snap = llm_provider_health_snapshot()
    return {
        "ok": bool(snap.get("running")),
        "url": None,
        "status_code": 200 if snap.get("running") else None,
        "error": snap.get("error"),
    }


def qdrant_port_from_url(url: str) -> int:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return int(parsed.port or 6333)


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
    # Hardening: Qdrant writes persistent data only to the named volume mounted
    # at /qdrant/storage. Keep root (official image default) but restrict the
    # runtime surface: read-only root FS, drop all capabilities, no new
    # privileges, and a writable tmpfs for temporary files.
    # The /tmp path is a container-local tmpfs mount, not a host temp dir.
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
        user="0:0",
        read_only_root_fs=True,
        cap_drop=["ALL"],
        no_new_privileges=True,
        tmpfs=["/tmp"],  # nosec B108
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


class RagRuntime:
    """Owns start/stop/status for Qdrant and runtime health (LLM provider via extension runtime)."""

    def __init__(self, config: RagRuntimeConfig | None = None) -> None:
        self._cfg = config or RagRuntimeConfig.from_env()

    @property
    def cfg(self) -> RagRuntimeConfig:
        return self._cfg

    def health(self) -> dict[str, Any]:
        cfg = self._cfg
        llm = llm_provider_health_snapshot()
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
        q_container = False
        try:
            from rag_service.qdrant_health_monitor import get_qdrant_health_monitor

            monitor = get_qdrant_health_monitor(self._cfg)
            if monitor.is_started:
                snap = monitor.get_snapshot()
                q_running_http = bool(snap.get("running"))
                q_http_status = snap.get("http_status")
                q_err = snap.get("error")
                q_container = bool(snap.get("container_running"))
            else:
                raise RuntimeError("monitor not started")
        except Exception:
            try:
                r = requests.get(f"{cfg.qdrant_http_url.rstrip('/')}/collections", timeout=3)
                q_running_http = r.ok
                q_http_status = r.status_code
            except requests.RequestException as e:
                q_err = str(e)
            with contextlib.suppress(Exception):
                q_container = container_is_running(cfg.qdrant_container_name)

        llm_component = {
            "running": bool(llm.get("running")),
            "provider_id": llm.get("provider_id"),
            "error": llm.get("error"),
        }
        return {
            "llm_provider": llm_component,
            "ollama": llm_component,
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
        _llm_removed = (
            False,
            "LLM provider is started from ChironAI (provider extension); rag-service no longer starts it.",
        )
        for name in services:
            n = name.strip().lower()
            if n in {"ollama", "llm", "llm_provider", "provider"}:
                results["ollama"] = _llm_removed
                results["llm_provider"] = _llm_removed
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
