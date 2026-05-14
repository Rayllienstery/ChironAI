"""Public ServiceStarter API."""

from __future__ import annotations

import sys
from typing import Any

import requests

from servicestarter.config import ServiceStarterConfig
from servicestarter import docker_ops
from servicestarter import ollama_ops
from servicestarter import windows_install


class ServiceStarter:
    """Install (Windows) and start Docker engine and Qdrant. Ollama is managed from the ChironAI app."""

    def __init__(self, config: ServiceStarterConfig | None = None) -> None:
        self._cfg = config or ServiceStarterConfig.from_env()

    @property
    def cfg(self) -> ServiceStarterConfig:
        return self._cfg

    def status(self) -> dict[str, Any]:
        """Aggregate status: ollama, docker, and qdrant."""
        cfg = self._cfg
        ollama_ping = ollama_ops.ollama_ping(cfg.ollama_base_url, timeout=3.0)

        docker_cli = False
        docker_engine = False
        docker_err: str | None = None
        try:
            docker_cli = docker_ops.docker_version_available()
            docker_engine = docker_ops.docker_engine_ready() if docker_cli else False
        except Exception as e:
            docker_err = str(e)

        q_running_http = False
        q_err: str | None = None
        try:
            r = requests.get(f"{cfg.qdrant_http_url.rstrip('/')}/collections", timeout=3)
            q_running_http = r.ok
            q_http_status = r.status_code
        except requests.RequestException as e:
            q_http_status = None
            q_err = str(e)

        q_container = False
        try:
            q_container = docker_ops.container_is_running(cfg.qdrant_container_name)
        except Exception:
            pass

        return {
            "ollama": {
                "running": bool(ollama_ping.get("ok")),
                "port": ollama_ops.ollama_port_from_base_url(cfg.ollama_base_url),
                "url": cfg.ollama_base_url,
                "http_status": ollama_ping.get("status_code"),
                "error": ollama_ping.get("error"),
            },
            "docker": {
                "cli_available": docker_cli,
                "engine_available": docker_engine,
                "error": docker_err,
            },
            "qdrant": {
                "running": q_running_http,
                "container_running": q_container,
                "port": docker_ops.qdrant_port_from_url(cfg.qdrant_http_url),
                "url": cfg.qdrant_http_url,
                "container": cfg.qdrant_container_name,
                "http_status": q_http_status,
                "error": q_err,
            },
        }

    def ensure_docker_installed(self) -> tuple[bool, str]:
        if docker_ops.docker_version_available():
            return True, "docker cli already present"
        if sys.platform != "win32":
            return (
                False,
                "docker CLI not found; install Docker Engine for your OS (automated install is Windows only)",
            )
        return windows_install.ensure_docker_desktop_installed(self._cfg.docker_desktop_installer_url)

    def ensure_docker_running(self) -> tuple[bool, str]:
        ok, msg = docker_ops.wait_for_docker_engine(
            self._cfg,
            start_desktop_on_windows=(sys.platform == "win32"),
        )
        return ok, msg

    def ensure_ollama_installed(self) -> tuple[bool, str]:
        if ollama_ops.find_ollama_executable():
            return True, "ollama already in PATH"
        if sys.platform != "win32":
            return False, "automated Ollama install is only implemented for Windows"
        return windows_install.ensure_ollama_installed(self._cfg.ollama_installer_url)

    def start_qdrant(self) -> tuple[bool, str]:
        ok_d, msg_d = self.ensure_docker_running()
        if not ok_d:
            return False, f"docker: {msg_d}"
        ok, msg = docker_ops.ensure_qdrant_container(self._cfg)
        if ok:
            docker_ops.wait_for_http_json(
                self._cfg.qdrant_http_url,
                path="/collections",
                timeout_sec=self._cfg.http_wait_timeout_sec,
            )
        return ok, msg

    def stop_qdrant(self) -> tuple[bool, str]:
        return docker_ops.docker_stop_container(self._cfg.qdrant_container_name)

    def start_all(self, services: list[str]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name in services:
            n = name.strip().lower()
            if n == "docker":
                results["docker_install"] = self.ensure_docker_installed()
                results["docker"] = self.ensure_docker_running()
            elif n == "ollama":
                results["ollama"] = (
                    False,
                    "Ollama Docker is started from the ChironAI app (Ollama tab); servicestarter no longer starts it.",
                )
            elif n == "qdrant":
                results["qdrant"] = self.start_qdrant()
            else:
                results[n] = (False, f"unknown service: {name}")
        results["status"] = self.status()
        return results
