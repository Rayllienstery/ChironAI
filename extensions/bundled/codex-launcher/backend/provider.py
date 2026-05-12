"""Codex launcher tab for ChironAI LLM Proxy IDE builds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from application.codex_launcher import (
    CodexLauncherError,
    build_command_preview,
    check_proxy_reachable,
    codex_config_path,
    codex_home,
    codex_status,
    ide_builds,
    load_builds,
    proxy_base_url,
    proxy_key_status,
    reveal_existing_proxy_key,
    selected_ide_build,
    write_codex_profile,
)
from config import get_server_port


def _manifest_tab_ui(manifest: Any) -> dict[str, Any]:
    metadata = getattr(manifest, "metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("tab_ui"), dict):
        return dict(metadata["tab_ui"])
    raw = getattr(manifest, "tab_ui", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _tab_title(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("title") or fallback).strip() or fallback


def _tab_icon(manifest: Any, fallback: str) -> str:
    tab_ui = _manifest_tab_ui(manifest)
    return str(tab_ui.get("icon") or getattr(manifest, "icon", "") or fallback).strip() or fallback


def _bool_text(value: Any) -> str:
    return "yes" if bool(value) else "no"


class CodexLauncherExtension:
    def __init__(self, host_context: Any, manifest: Any) -> None:
        self._host = host_context
        self._manifest = manifest

    def _settings_repo(self) -> Any:
        return self._host.get_settings_repository()

    def _diagnostics(self, *, ping_proxy: bool = True) -> dict[str, Any]:
        repo = self._settings_repo()
        base_url = proxy_base_url(get_server_port())
        codex = codex_status()
        key_status = proxy_key_status(repo)
        builds = ide_builds(load_builds(repo))
        proxy = {
            "ok": False,
            "status": "unchecked" if not ping_proxy else "unreachable",
            "message": "Proxy check skipped" if not ping_proxy else "",
        }
        if ping_proxy and bool(key_status.get("configured")) and bool(key_status.get("recoverable")):
            try:
                api_key = reveal_existing_proxy_key(repo)
                check_proxy_reachable(base_url, api_key, timeout=0.75)
                proxy = {"ok": True, "status": "ok", "message": "Proxy reachable"}
            except Exception as e:
                proxy = {"ok": False, "status": "error", "message": str(e)}
        elif ping_proxy:
            proxy["message"] = "API key is missing or not recoverable"
        return {
            "base_url": base_url,
            "codex_home": str(codex_home()),
            "config_path": str(codex_config_path()),
            "codex": codex,
            "api_key": key_status,
            "proxy": proxy,
            "ide_builds_count": len(builds),
            "ide_builds": builds,
        }

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        diag = self._diagnostics(ping_proxy=False)
        codex_ok = bool((diag.get("codex") or {}).get("installed"))
        key_ok = bool((diag.get("api_key") or {}).get("recoverable"))
        count = int(diag.get("ide_builds_count") or 0)
        ok = codex_ok and key_ok and count > 0
        message = "ready" if ok else "needs setup"
        return {
            "id": "codex",
            "title": _tab_title(self._manifest, "Codex"),
            "icon": _tab_icon(self._manifest, "icons/codex-light.svg"),
            "description": "Configure Codex to use ChironAI LLM Proxy IDE builds.",
            "frame": {},
            "order": 55,
            "status": {
                "running": ok,
                "tone": "success" if ok else "warning",
                "message": message,
                "codex_installed": codex_ok,
                "api_key_configured": key_ok,
                "ide_builds_count": count,
            },
        }

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        diag = self._diagnostics(ping_proxy=True)
        builds = list(diag.get("ide_builds") or [])
        selected = str((builds[0] if builds else {}).get("id") or "")
        command = build_command_preview(selected) if selected else "chironai codex"
        key_status = dict(diag.get("api_key") or {})
        proxy = dict(diag.get("proxy") or {})
        codex = dict(diag.get("codex") or {})

        codex_installed = bool(codex.get("installed"))
        key_ok = bool(key_status.get("recoverable"))
        has_ide_builds = bool(builds)

        status_components = [
            {
                "type": "status",
                "key": "codex_installed",
                "label": "Codex installed",
                "status": "ok" if codex.get("installed") else "missing",
                "message": (
                    str(codex.get("version") or codex.get("path") or "ok")
                    if codex.get("installed")
                    else "Install: npm install -g @openai/codex"
                ),
            },
            {
                "type": "status",
                "key": "proxy_reachable",
                "label": "Proxy reachable",
                "status": "ok" if proxy.get("ok") else str(proxy.get("status") or "error"),
                "message": str(proxy.get("message") or ""),
            },
            {
                "type": "status",
                "key": "api_key_configured",
                "label": "API key configured",
                "status": "ok" if key_status.get("recoverable") else "missing",
                "message": (
                    f"Prefix: {key_status.get('prefix')}"
                    if key_status.get("recoverable")
                    else "Use RAG Fusion Proxy -> Overview -> Security"
                ),
            },
            {
                "type": "status",
                "key": "ide_builds_count",
                "label": "IDE builds count",
                "status": "ok" if builds else "empty",
                "message": str(len(builds)),
            },
            {
                "type": "text",
                "key": "proxy_url",
                "label": "Proxy URL",
                "value": str(diag.get("base_url") or ""),
            },
            {
                "type": "text",
                "key": "config_path",
                "label": "Config",
                "value": str(diag.get("config_path") or ""),
            },
        ]

        build_components: list[dict[str, Any]]
        if builds:
            build_components = [
                {
                    "type": "select",
                    "key": "selected_build",
                    "label": "Selected build",
                    "value": selected,
                    "options": [
                        {
                            "value": str(item.get("id") or ""),
                            "label": str(item.get("display_name") or item.get("id") or ""),
                        }
                        for item in builds
                    ],
                },
                {
                    "type": "text",
                    "key": "command_preview",
                    "label": "Command",
                    "value": command,
                },
                {
                    "type": "action",
                    "key": "configure_codex",
                    "label": "Configure Codex",
                    "action_id": "configure_codex",
                    "variant": "primary",
                    "payload_keys": ["selected_build"],
                },
                {
                    "type": "action",
                    "key": "copy_command",
                    "label": "Copy command",
                    "action_id": "copy_command",
                    "variant": "secondary",
                    "payload_keys": ["selected_build"],
                },
                {
                    "type": "table",
                    "key": "codex_ide_builds",
                    "label": "IDE builds",
                    "columns": [
                        {"key": "id", "label": "Build ID"},
                        {"key": "display_name", "label": "Display name"},
                        {"key": "provider_model", "label": "Provider/model"},
                        {"key": "context_length", "label": "Context"},
                        {"key": "private", "label": "Private"},
                        {"key": "streaming", "label": "Streaming"},
                        {"key": "health", "label": "Health"},
                    ],
                    "rows": [self._build_row(item) for item in builds],
                },
            ]
        else:
            build_components = [
                {
                    "type": "status",
                    "key": "empty_state",
                    "label": "No IDE builds",
                    "status": "empty",
                    "message": "Enable IDE mode in LLM Proxy Builds -> Agent Proxy Mode.",
                }
            ]

        all_ready = codex_installed and key_ok and has_ide_builds
        setup_steps = [
            {
                "id": "install_codex",
                "label": "Install Codex CLI",
                "status": "done" if codex_installed else "todo",
                "command": None if codex_installed else "npm install -g @openai/codex",
            },
            {
                "id": "configure_key",
                "label": "Configure API key",
                "status": "done" if key_ok else "todo",
                "hint": None if key_ok else "RAG Fusion Proxy → Overview → Security",
            },
            {
                "id": "enable_ide_build",
                "label": "Enable IDE mode on a build",
                "status": "done" if has_ide_builds else "todo",
                "hint": None if has_ide_builds else "LLM Proxy Builds → Agent Proxy Mode",
            },
            {
                "id": "launch",
                "label": "Launch Codex",
                "status": "done" if all_ready else "todo",
                "command": command if all_ready else None,
                "hint": None if all_ready else "Complete the steps above, then run the command shown here",
            },
        ]

        schema = {
            "pages": [
                {
                    "id": "codex-overview",
                    "title": "Codex",
                    "sections": [
                        {
                            "id": "setup",
                            "title": "Getting Started",
                            "components": [
                                {
                                    "type": "steps",
                                    "key": "setup_guide",
                                    "steps": setup_steps,
                                }
                            ],
                        },
                        {"id": "status", "title": "Status", "components": status_components},
                        {"id": "builds", "title": "IDE Builds", "components": build_components},
                        {
                            "id": "diagnostics",
                            "title": "Diagnostics",
                            "components": [
                                {
                                    "type": "diagnostics",
                                    "key": "codex_diagnostics",
                                    "label": "Codex diagnostics",
                                    "summary": False,
                                    "value": diag,
                                }
                            ],
                        },
                    ],
                }
            ]
        }
        return {
            "title": _tab_title(self._manifest, "Codex"),
            "icon": _tab_icon(self._manifest, "icons/codex-light.svg"),
            "frame": {},
            "status": {
                "running": bool(proxy.get("ok")),
                "tone": "success" if bool(proxy.get("ok")) else "warning",
                "message": str(proxy.get("message") or proxy.get("status") or ""),
            },
            "schema": schema,
            "state": {
                "extension_id": str(getattr(self._manifest, "id", "codex-launcher") or "codex-launcher"),
                "selected_build": selected,
                "command": command,
            },
        }

    def run_action(self, action_id: str, payload: dict[str, Any], *, runtime: Any | None = None) -> dict[str, Any]:
        action = str(action_id or "").strip()
        if action == "refresh":
            return {"ok": True, "message": "Refreshed", "diagnostics": self._diagnostics(ping_proxy=True)}
        builds = ide_builds(load_builds(self._settings_repo()))
        selected = str(payload.get("selected_build") or payload.get("model") or "").strip()
        if not selected and builds:
            selected = str(builds[0].get("id") or "").strip()
        if not selected:
            raise CodexLauncherError("No IDE-enabled builds found. Enable IDE mode in LLM Proxy Builds -> Agent Proxy Mode.")
        build = selected_ide_build(builds, selected)
        build_id = str(build.get("id") or "").strip()
        command = build_command_preview(build_id)
        if action == "copy_command":
            return {"ok": True, "message": command, "command": command}
        if action == "configure_codex":
            reveal_existing_proxy_key(self._settings_repo())
            base_url = proxy_base_url(get_server_port())
            raw_config_path = str(payload.get("config_path") or "").strip()
            config_path = Path(raw_config_path) if raw_config_path else None
            written = write_codex_profile(base_url, config_path=config_path, build=build)
            return {
                "ok": True,
                "message": f"Configured Codex profile for {build_id}",
                "config_path": str(written),
                "base_url": base_url,
                "command": command,
            }
        raise ValueError(f"Unsupported action: {action}")

    def _build_row(self, build: dict[str, Any]) -> dict[str, Any]:
        provider = str(build.get("provider_id") or "")
        model = str(build.get("model") or build.get("ollama_model") or "")
        issues = build.get("issues") if isinstance(build.get("issues"), list) else []
        return {
            "id": str(build.get("id") or ""),
            "display_name": str(build.get("display_name") or build.get("id") or ""),
            "provider_model": f"{provider}/{model}" if provider or model else "",
            "context_length": build.get("num_ctx") or build.get("context_length") or "",
            "private": _bool_text(build.get("private")),
            "streaming": _bool_text(build.get("sse_streaming", True)),
            "health": "ok" if not issues and build.get("healthy", True) is not False else "; ".join(str(x) for x in issues),
        }


def create_provider(host_context: Any, manifest: Any) -> CodexLauncherExtension:
    return CodexLauncherExtension(host_context, manifest)
