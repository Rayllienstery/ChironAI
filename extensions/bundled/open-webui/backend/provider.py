"""Open WebUI extension.

The host only sees a generic extension tab. Docker/container ownership stays in
this bundled extension so the core app can remove or update it independently.
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

LEGACY_BACKEND_KEY = "open_webui_ollama_base_url"
BACKEND_KEY = "extensions.open-webui.ollama_base_url"


def _as_int(raw: str | None, default: int) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return default


def _normalize_backend_url(raw: str) -> str:
    s = (raw or "").strip().rstrip("/")
    if not s:
        raise ValueError("URL is empty")
    if "://" not in s:
        s = f"http://{s}"
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("URL must include a host")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}".rstrip("/")


@dataclass(frozen=True)
class OpenWebUiConfig:
    container_name: str
    host_url: str
    image: str
    host_port: int
    container_port: int
    ollama_url_for_container: str


class DockerRunner:
    def _docker_executable(self) -> str:
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

    def run(self, args: list[str], *, timeout: float = 30.0) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                [self._docker_executable(), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return int(proc.returncode), proc.stdout.strip(), proc.stderr.strip()
        except FileNotFoundError:
            return 127, "", "Docker CLI not found"
        except subprocess.TimeoutExpired as e:
            return 124, e.stdout or "", e.stderr or "Docker command timed out"

    def container_running(self, name: str) -> tuple[bool, str]:
        code, out, err = self.run(["inspect", "-f", "{{.State.Running}}", name], timeout=8.0)
        if code == 0:
            return out.strip().lower() == "true", ""
        if "no such object" in err.lower() or "no such object" in out.lower():
            return False, ""
        return False, err or out

    def container_exists(self, name: str) -> bool:
        code, _out, _err = self.run(["inspect", name], timeout=8.0)
        return code == 0

    def container_env(self, name: str, key: str) -> str:
        code, out, _err = self.run(
            ["inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", name],
            timeout=8.0,
        )
        if code != 0:
            return ""
        prefix = f"{key}="
        for line in out.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return ""

    def start_container(self, name: str) -> tuple[bool, str]:
        code, out, err = self.run(["start", name], timeout=30.0)
        if code == 0:
            return True, out or "started"
        if "already running" in err.lower():
            return True, "already running"
        return False, err or out

    def stop_container(self, name: str) -> tuple[bool, str]:
        code, out, err = self.run(["stop", name], timeout=30.0)
        if code == 0:
            return True, out or "stopped"
        return False, err or out

    def remove_container(self, name: str) -> tuple[bool, str]:
        code, out, err = self.run(["rm", "-f", name], timeout=30.0)
        if code == 0:
            return True, out or "removed"
        if "no such" in (err or out).lower():
            return True, "not present"
        return False, err or out

    def pull_image(self, image: str) -> tuple[bool, str]:
        code, out, err = self.run(["pull", image], timeout=300.0)
        if code == 0:
            return True, out or "pulled"
        return False, err or out

    def run_container(self, cfg: OpenWebUiConfig) -> tuple[bool, str]:
        extra_hosts: list[str] = []
        if sys.platform != "win32":
            extra_hosts = ["--add-host", "host.docker.internal:host-gateway"]
        code, out, err = self.run(
            [
                "run",
                "-d",
                "--name",
                cfg.container_name,
                "-p",
                f"{cfg.host_port}:{cfg.container_port}",
                "-e",
                f"OLLAMA_BASE_URL={cfg.ollama_url_for_container}",
                "--restart",
                "unless-stopped",
                *extra_hosts,
                cfg.image,
            ],
            timeout=60.0,
        )
        if code == 0:
            return True, out or "started"
        return False, err or out


class OpenWebUiExtension:
    def __init__(self, host_context: Any, manifest: Any, docker: DockerRunner | None = None) -> None:
        self._host = host_context
        self._manifest = manifest
        self._docker = docker or DockerRunner()

    def _settings_repo(self) -> Any:
        return self._host.get_settings_repository()

    def _server_port(self) -> int:
        raw = (
            os.getenv("WEBUI_PORT")
            or os.getenv("PORT")
            or os.getenv("CHIRONAI_WEBUI_PORT")
            or "8080"
        )
        return _as_int(raw, 8080)

    def _default_ollama_for_container(self) -> str:
        ollama_port = _as_int(os.getenv("OLLAMA_PORT"), 11343)
        raw_base = (os.getenv("OLLAMA_BASE_URL") or "").strip().rstrip("/")
        if raw_base:
            parsed = urlparse(raw_base if "://" in raw_base else f"http://{raw_base}")
            port = parsed.port or ollama_port
            return f"http://host.docker.internal:{port}"
        return f"http://host.docker.internal:{ollama_port}"

    def _saved_backend_url(self) -> str:
        repo = self._settings_repo()
        current = str(repo.get_app_setting(BACKEND_KEY) or "").strip()
        if current:
            return current
        legacy = str(repo.get_app_setting(LEGACY_BACKEND_KEY) or "").strip()
        if legacy:
            try:
                normalized = _normalize_backend_url(legacy)
            except ValueError:
                normalized = legacy.rstrip("/")
            repo.set_app_setting(BACKEND_KEY, normalized)
            repo.set_app_setting(LEGACY_BACKEND_KEY, "")
            return normalized
        return ""

    def _config(self) -> OpenWebUiConfig:
        host_url = (os.getenv("OPEN_WEBUI_URL") or "http://localhost:3000").rstrip("/")
        host_port = _as_int(os.getenv("OPEN_WEBUI_HOST_PORT"), 3000)
        container_port = _as_int(os.getenv("OPEN_WEBUI_CONTAINER_PORT"), 8080)
        env_backend = (os.getenv("OPEN_WEBUI_OLLAMA_BASE_URL") or "").strip().rstrip("/")
        saved = self._saved_backend_url()
        return OpenWebUiConfig(
            container_name=os.getenv("OPEN_WEBUI_CONTAINER_NAME", "open-webui"),
            host_url=host_url,
            image=os.getenv("OPEN_WEBUI_IMAGE", "open-webui/open-webui:main"),
            host_port=host_port,
            container_port=container_port,
            ollama_url_for_container=(saved or env_backend or self._default_ollama_for_container()).rstrip("/"),
        )

    def _status(self, *, ping: bool = False) -> dict[str, Any]:
        cfg = self._config()
        running, err = self._docker.container_running(cfg.container_name)
        status: dict[str, Any] = {
            "running": bool(running),
            "tone": "success" if running else "neutral",
            "message": "running" if running else "stopped",
            "updated_at": int(time.time()),
            "url": cfg.host_url,
        }
        if err:
            status.update({"tone": "error", "message": err})
        if ping and running:
            try:
                resp = requests.get(cfg.host_url.rstrip("/") + "/", timeout=0.8)
                status["http_status"] = resp.status_code
            except Exception as e:
                status["http_error"] = str(e)
        return status

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        return {
            "id": "open-webui",
            "title": "Open WebUI",
            "icon": "icons/open-webui-light.svg",
            "description": "Open WebUI iframe tab managed by its own extension runtime.",
            "order": 60,
            "status": self._status(ping=False),
        }

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        cfg = self._config()
        status = self._status(ping=True)
        env_set = bool((os.getenv("OPEN_WEBUI_OLLAMA_BASE_URL") or "").strip())
        saved = self._saved_backend_url()
        source = "saved" if saved else "environment" if env_set else "default"
        llm_proxy_hint = f"http://host.docker.internal:{self._server_port()}"
        running = bool(status.get("running"))
        return {
            "title": "Open WebUI",
            "icon": "icons/open-webui-light.svg",
            "status": status,
            "content": {
                "type": "iframe",
                "src": cfg.host_url,
                "open_external_url": cfg.host_url,
                "title": "Open WebUI",
                "fields": [
                    {
                        "key": "backend_url",
                        "label": "Chat backend URL",
                        "value": cfg.ollama_url_for_container,
                        "placeholder": llm_proxy_hint,
                    }
                ],
                "actions": [
                    {"id": "refresh", "label": "Refresh", "variant": "secondary"},
                    {
                        "id": "start",
                        "label": "Start service",
                        "variant": "primary",
                        "disabled": running,
                    },
                    {
                        "id": "stop",
                        "label": "Stop service",
                        "variant": "danger",
                        "disabled": not running,
                        "confirm": "Stop Open WebUI container?",
                    },
                    {
                        "id": "save_backend",
                        "label": "Save backend",
                        "variant": "primary",
                        "payload_keys": ["backend_url"],
                    },
                    {
                        "id": "clear_backend",
                        "label": "Clear saved backend",
                        "variant": "secondary",
                    },
                    {
                        "id": "open_external",
                        "label": "Open external",
                        "variant": "secondary",
                    },
                ],
                "details": [
                    {"label": "Container", "value": cfg.container_name},
                    {"label": "Image", "value": cfg.image},
                    {"label": "Host URL", "value": cfg.host_url},
                    {"label": "Container port", "value": str(cfg.container_port)},
                    {"label": "Backend source", "value": source},
                    {"label": "LLM Proxy hint", "value": llm_proxy_hint},
                ],
            },
        }

    def _ensure_container(self, cfg: OpenWebUiConfig) -> tuple[bool, str]:
        running, err = self._docker.container_running(cfg.container_name)
        if err:
            return False, err
        if running:
            current = self._docker.container_env(cfg.container_name, "OLLAMA_BASE_URL").rstrip("/")
            if current and current != cfg.ollama_url_for_container:
                ok_rm, msg_rm = self._docker.remove_container(cfg.container_name)
                if not ok_rm:
                    return False, msg_rm
            else:
                return True, "already running"
        elif self._docker.container_exists(cfg.container_name):
            current = self._docker.container_env(cfg.container_name, "OLLAMA_BASE_URL").rstrip("/")
            if current and current != cfg.ollama_url_for_container:
                ok_rm, msg_rm = self._docker.remove_container(cfg.container_name)
                if not ok_rm:
                    return False, msg_rm
            else:
                return self._docker.start_container(cfg.container_name)
        ok_pull, msg_pull = self._docker.pull_image(cfg.image)
        if not ok_pull:
            return False, msg_pull
        return self._docker.run_container(cfg)

    def run_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        *,
        runtime: Any | None = None,
    ) -> dict[str, Any]:
        action = str(action_id or "").strip()
        cfg = self._config()
        if action == "refresh":
            return {"ok": True, "message": "Refreshed", "status": self._status(ping=True)}
        if action == "open_external":
            return {"ok": True, "message": cfg.host_url, "open_external_url": cfg.host_url}
        if action == "start":
            ok, msg = self._ensure_container(cfg)
            return {"ok": bool(ok), "message": msg, "status": self._status(ping=True)}
        if action == "stop":
            ok, msg = self._docker.stop_container(cfg.container_name)
            return {"ok": bool(ok), "message": msg, "status": self._status(ping=True)}
        if action == "save_backend":
            raw = str(payload.get("backend_url") or "").strip()
            norm = _normalize_backend_url(raw)
            self._settings_repo().set_app_setting(BACKEND_KEY, norm)
            return {
                "ok": True,
                "message": "Saved. Start or restart Open WebUI to apply the backend URL.",
                "backend_url": norm,
            }
        if action == "clear_backend":
            self._settings_repo().set_app_setting(BACKEND_KEY, "")
            return {"ok": True, "message": "Cleared saved backend URL."}
        raise ValueError(f"Unsupported action: {action}")


def create_provider(host_context: Any, manifest: Any) -> OpenWebUiExtension:
    return OpenWebUiExtension(host_context, manifest)
