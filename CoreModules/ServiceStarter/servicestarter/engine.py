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
    """Install (Windows) and start Docker engine, Ollama, Qdrant, Open WebUI."""

    def __init__(self, config: ServiceStarterConfig | None = None) -> None:
        self._cfg = config or ServiceStarterConfig.from_env()

    @property
    def cfg(self) -> ServiceStarterConfig:
        return self._cfg

    def status(self) -> dict[str, Any]:
        """Aggregate status: ollama, docker, qdrant (container + http), open_webui."""
        cfg = self._cfg
        ollama_ping = ollama_ops.ollama_ping(cfg.ollama_base_url, timeout=3.0)

        docker_cli = docker_ops.docker_version_available()
        docker_engine = docker_ops.docker_engine_ready() if docker_cli else False

        q_running_http = False
        q_err: str | None = None
        try:
            r = requests.get(f"{cfg.qdrant_http_url.rstrip('/')}/collections", timeout=3)
            q_running_http = r.ok
            q_http_status = r.status_code
        except requests.RequestException as e:
            q_http_status = None
            q_err = str(e)

        q_container = docker_ops.container_name_matches_running(cfg.qdrant_container_name)

        ow_running_container = docker_ops.container_name_matches_running(cfg.open_webui_container_name)
        ow_http_status: int | None = None
        ow_http_err: str | None = None
        try:
            rr = requests.get(cfg.open_webui_host_url.rstrip("/") + "/", timeout=2)
            ow_http_status = rr.status_code
        except requests.RequestException as e:
            ow_http_err = str(e)

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
            "open_webui": {
                "running": ow_running_container,
                "port": docker_ops.open_webui_port_from_url(cfg.open_webui_host_url),
                "url": cfg.open_webui_host_url,
                "container": cfg.open_webui_container_name,
                "http_status": ow_http_status,
                "http_error": ow_http_err,
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

    def start_ollama(self) -> tuple[bool, str]:
        ping = ollama_ops.ollama_ping(self._cfg.ollama_base_url, timeout=2.0)
        if ping.get("ok"):
            return True, "already running"
        return ollama_ops.start_ollama_serve(self._cfg)

    def stop_ollama(self) -> tuple[bool, str]:
        return ollama_ops.stop_ollama_process()

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

    def start_open_webui(self) -> tuple[bool, str]:
        ok_d, msg_d = self.ensure_docker_running()
        if not ok_d:
            return False, f"docker: {msg_d}"
        ok, msg = docker_ops.ensure_open_webui_container(self._cfg)
        if ok:
            docker_ops.wait_for_http_json(
                self._cfg.open_webui_host_url,
                path="/",
                ok_status=(200, 301, 302, 304),
                timeout_sec=self._cfg.http_wait_timeout_sec,
            )
        return ok, msg

    def stop_open_webui(self) -> tuple[bool, str]:
        return docker_ops.docker_stop_container(self._cfg.open_webui_container_name)

    def start_all(self, services: list[str]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name in services:
            n = name.strip().lower()
            if n == "docker":
                results["docker_install"] = self.ensure_docker_installed()
                results["docker"] = self.ensure_docker_running()
            elif n == "ollama":
                results["ollama_install"] = self.ensure_ollama_installed()
                results["ollama"] = self.start_ollama()
            elif n == "qdrant":
                results["qdrant"] = self.start_qdrant()
            elif n in ("open-webui", "open_webui", "webui"):
                results["open_webui"] = self.start_open_webui()
            else:
                results[n] = (False, f"unknown service: {name}")
        results["status"] = self.status()
        return results
