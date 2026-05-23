"""Open WebUI extension.

The host only sees a generic extension tab. Docker/container ownership stays in
this bundled extension so the core app can remove or update it independently.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import requests

LEGACY_BACKEND_KEY = "open_webui_ollama_base_url"
BACKEND_KEY = "extensions.open-webui.ollama_base_url"
DEFAULT_OPEN_WEBUI_IMAGE = "ghcr.io/open-webui/open-webui:main"


def _manifest_tab_ui(manifest: Any) -> dict[str, Any]:
    metadata = getattr(manifest, "metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("tab_ui"), dict):
        return dict(metadata["tab_ui"])
    raw = getattr(manifest, "tab_ui", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _tab_frame(manifest: Any) -> dict[str, Any]:
    tab_ui = _manifest_tab_ui(manifest)
    frame = tab_ui.get("frame")
    return dict(frame) if isinstance(frame, dict) else {}


def _tab_title(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("title") or fallback).strip() or fallback


def _tab_icon(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("icon") or getattr(manifest, "icon", "") or fallback).strip() or fallback


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
    openai_base_url_for_container: str
    volumes: list[str]


class OpenWebUiExtension:
    def __init__(self, host_context: Any, manifest: Any, docker: Any | None = None) -> None:
        self._host = host_context
        self._manifest = manifest
        self._docker_override = docker

    def _settings_repo(self) -> Any:
        return self._host.get_settings_repository()

    def _server_port(self) -> int:
        raw = (
            os.getenv("SERVER_PORT")
            or os.getenv("CHIRONAI_PROXY_PORT")
            or os.getenv("PORT")
            or os.getenv("CHIRONAI_WEBUI_PORT")
        )
        if raw:
            return _as_int(raw, 8080)
        try:
            from config import get_active_server_port

            return int(get_active_server_port())
        except Exception:
            return 8080

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
            image=os.getenv("OPEN_WEBUI_IMAGE", DEFAULT_OPEN_WEBUI_IMAGE),
            host_port=host_port,
            container_port=container_port,
            ollama_url_for_container=(saved or env_backend or self._default_ollama_for_container()).rstrip("/"),
            openai_base_url_for_container=f"http://host.docker.internal:{self._server_port()}/v1",
            volumes=[os.getenv("OPEN_WEBUI_DATA_VOLUME", "open-webui") + ":/app/backend/data"],
        )

    def _chiron_openai_api_key(self, *, create_if_missing: bool = False) -> tuple[str, str]:
        """Return (key, state) for OpenWebUI's OpenAI-compatible Chiron provider."""
        try:
            from llm_proxy.api_key import (
                generate_proxy_api_key_record,
                proxy_api_key_status,
                reveal_proxy_api_key,
                store_proxy_api_key_record,
            )
        except Exception:
            return "", "unavailable"

        repo = self._settings_repo()
        status = proxy_api_key_status(repo)
        if bool(status.get("configured")) and bool(status.get("recoverable")):
            return reveal_proxy_api_key(repo).strip(), "recoverable"
        if not bool(status.get("configured")) and create_if_missing:
            plaintext, record = generate_proxy_api_key_record(repo)
            store_proxy_api_key_record(repo, record)
            return plaintext.strip(), "generated"
        if bool(status.get("configured")):
            return "", "not recoverable"
        return "", "missing"

    def _docker_runtime(self) -> Any | None:
        if self._docker_override is not None:
            return self._docker_override
        runtime = getattr(self._host, "docker_runtime", None)
        if runtime is not None:
            return runtime
        metadata = getattr(self._host, "metadata", {}) or {}
        if isinstance(metadata, dict):
            return metadata.get("docker_runtime")
        return None

    def _docker_unavailable(self) -> dict[str, Any]:
        return {
            "ok": False,
            "message": "Docker runtime is unavailable",
            "error": "Docker runtime is unavailable",
        }

    def _docker_spec(self, cfg: OpenWebUiConfig, *, chiron_api_key: str | None = None) -> Any:
        from docker_manager import DockerContainerSpec

        extra_hosts: list[str] = []
        if sys.platform != "win32":
            extra_hosts = ["host.docker.internal:host-gateway"]
        if chiron_api_key is None:
            chiron_api_key, _state = self._chiron_openai_api_key(create_if_missing=True)
        env = {
            "OLLAMA_BASE_URL": cfg.ollama_url_for_container,
            "ENABLE_OPENAI_API": "True",
            "OPENAI_API_BASE_URLS": cfg.openai_base_url_for_container,
            "OPENAI_API_KEYS": chiron_api_key,
        }
        return DockerContainerSpec(
            name=cfg.container_name,
            image=cfg.image,
            ports=[f"{cfg.host_port}:{cfg.container_port}"],
            env=env,
            volumes=cfg.volumes,
            restart="unless-stopped",
            extra_hosts=extra_hosts,
            labels={
                "chironai.extension": str(getattr(self._manifest, "id", "open-webui") or "open-webui"),
                "chironai.provider": "open-webui",
            },
        )

    def _runtime_config(self, cfg: OpenWebUiConfig) -> OpenWebUiConfig:
        """Prefer the already-created container image when the default image cannot be pulled."""
        if (os.getenv("OPEN_WEBUI_IMAGE") or "").strip():
            return cfg
        docker = self._docker_runtime()
        if docker is None:
            return cfg
        try:
            state = docker.inspect_container(cfg.container_name)
            if bool(getattr(state, "exists", False)):
                image = str(getattr(state, "image", "") or "").strip()
                raw_volumes = getattr(state, "volumes", None)
                volumes = [str(v).strip() for v in raw_volumes or [] if str(v).strip()]
                if not volumes:
                    volumes = cfg.volumes
                if image:
                    return replace(cfg, image=image, volumes=volumes)
        except Exception:
            pass
        return cfg

    def _status(self, *, ping: bool = False) -> dict[str, Any]:
        cfg = self._config()
        docker = self._docker_runtime()
        running = False
        status: dict[str, Any] = {
            "running": False,
            "tone": "neutral",
            "message": "stopped",
            "updated_at": int(time.time()),
            "url": cfg.host_url,
        }
        if docker is None:
            status.update({"tone": "error", "message": "Docker runtime is unavailable"})
            return status
        try:
            state = docker.inspect_container(cfg.container_name)
            exists = bool(getattr(state, "exists", False))
            running = bool(getattr(state, "running", False))
            status.update(
                {
                    "running": running,
                    "tone": "success" if running else "neutral",
                    "message": "running" if running else "stopped" if exists else "not created",
                }
            )
        except Exception as e:
            status.update({"tone": "error", "message": str(e)})
            return status
        if ping and running:
            try:
                resp = requests.get(cfg.host_url.rstrip("/") + "/", timeout=0.8)
                status["http_status"] = resp.status_code
            except Exception as e:
                status["http_error"] = str(e)
        return status

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        frame = _tab_frame(self._manifest)
        return {
            "id": "open-webui",
            "title": _tab_title(self._manifest, "Open WebUI"),
            "icon": _tab_icon(self._manifest, "icons/open-webui-light.svg"),
            "description": "Open WebUI iframe tab managed by its own extension runtime.",
            "frame": frame,
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
        _chiron_api_key, chiron_key_state = self._chiron_openai_api_key(create_if_missing=False)
        running = bool(status.get("running"))

        actions = [{"id": "refresh", "label": "Refresh", "variant": "secondary"}]
        if running:
            actions.append(
                {
                    "id": "apply_config",
                    "label": "Apply configuration",
                    "variant": "primary",
                    "confirm": "Recreate Open WebUI container with the current Chiron provider configuration?",
                }
            )
            actions.append(
                {
                    "id": "stop",
                    "label": "Stop service",
                    "variant": "danger",
                    "confirm": "Stop Open WebUI container?",
                }
            )
        else:
            actions.append(
                {
                    "id": "start",
                    "label": "Start service",
                    "variant": "primary",
                }
            )

        actions.extend(
            [
                {
                    "id": "clear_backend",
                    "label": "Clear saved backend",
                    "variant": "secondary",
                    "confirm": "Clear the saved backend URL? Open WebUI will fall back to env/default.",
                },
                {
                    "id": "open_external",
                    "label": "Open external",
                    "variant": "secondary",
                },
            ]
        )

        return {
            "title": _tab_title(self._manifest, "Open WebUI"),
            "icon": _tab_icon(self._manifest, "icons/open-webui-light.svg"),
            "frame": _tab_frame(self._manifest),
            "status": status,
            "content": {
                "type": "service_panel",
                "title": _tab_title(self._manifest, "Open WebUI"),
                "subtitle": "Docker-managed Open WebUI runtime",
                "open_external_url": cfg.host_url,
                "fields": [
                    {
                        "key": "backend_url",
                        "label": "Chat backend URL",
                        "value": cfg.ollama_url_for_container,
                        "placeholder": llm_proxy_hint,
                        "autosave_action_id": "save_backend",
                    }
                ],
                "actions": actions,
                "details": [
                    {"label": "Container", "value": cfg.container_name},
                    {"label": "Image", "value": cfg.image},
                    {"label": "Host URL", "value": cfg.host_url},
                    {"label": "Port", "value": f"{cfg.host_port}:{cfg.container_port}"},
                    {"label": "Backend source", "value": source},
                    {"label": "Chiron OpenAI URL", "value": cfg.openai_base_url_for_container},
                    {"label": "Chiron API key", "value": chiron_key_state},
                ],
            },
            "schema": {
                "pages": [
                    {
                        "id": "open-webui-settings",
                        "sections": [
                            {
                                "id": "open-webui-actions",
                                "title": "Open WebUI",
                                "components": [
                                    {
                                        "type": "status",
                                        "key": "status",
                                        "label": "Service",
                                        "status": "running" if running else "stopped",
                                        "message": str(status.get("message") or ""),
                                    },
                                    {
                                        "type": "input",
                                        "key": "backend_url",
                                        "label": "Chat backend URL",
                                        "value": cfg.ollama_url_for_container,
                                        "placeholder": llm_proxy_hint,
                                        "autosave_action_id": "save_backend",
                                    },
                                    *(
                                        [
                                            {
                                                "type": "action",
                                                "action_id": action["id"],
                                                "label": action.get("label"),
                                                "variant": action.get("variant"),
                                                "confirm": action.get("confirm"),
                                                "payload_keys": action.get("payload_keys"),
                                            }
                                            for action in actions
                                        ]
                                    ),
                                    {
                                        "type": "text",
                                        "key": "details",
                                        "label": "Details",
                                        "value": (
                                            f"Container={cfg.container_name} | "
                                            f"Image={cfg.image} | "
                                            f"Host URL={cfg.host_url} | "
                                            f"Container port={cfg.container_port} | "
                                            f"Backend source={source} | "
                                            f"Chiron OpenAI URL={cfg.openai_base_url_for_container} | "
                                            f"Chiron API key={chiron_key_state}"
                                        ),
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    def _ensure_container(self, cfg: OpenWebUiConfig) -> tuple[bool, str]:
        docker = self._docker_runtime()
        if docker is None:
            return False, "Docker runtime is unavailable"
        cfg = self._runtime_config(cfg)
        chiron_api_key, chiron_key_state = self._chiron_openai_api_key(create_if_missing=True)
        if not chiron_api_key:
            return (
                False,
                "Chiron proxy API key is "
                f"{chiron_key_state}. Generate or regenerate a recoverable key in RAG Fusion Proxy -> Security.",
            )
        result = docker.ensure_container(self._docker_spec(cfg, chiron_api_key=chiron_api_key))
        return bool(result.get("ok")), str(result.get("message") or result.get("details") or result.get("error") or "")

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
        if action in ("start", "apply_config"):
            ok, msg = self._ensure_container(cfg)
            return {"ok": bool(ok), "message": msg, "status": self._status(ping=True)}
        if action == "stop":
            docker = self._docker_runtime()
            if docker is None:
                unavailable = self._docker_unavailable()
                return {**unavailable, "status": self._status(ping=True)}
            result = docker.stop_container(cfg.container_name)
            return {
                "ok": bool(result.get("ok")),
                "message": result.get("message") or result.get("details") or result.get("error") or "",
                "status": self._status(ping=True),
            }
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
            refreshed = self._config()
            return {
                "ok": True,
                "message": "Cleared saved backend URL.",
                "backend_url": refreshed.ollama_url_for_container,
            }
        raise ValueError(f"Unsupported action: {action}")


def create_provider(host_context: Any, manifest: Any) -> OpenWebUiExtension:
    return OpenWebUiExtension(host_context, manifest)
