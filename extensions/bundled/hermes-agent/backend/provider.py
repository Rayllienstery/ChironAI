"""Hermes Agent extension.

The host only sees a generic extension tab. The Hermes gateway stays a native
host process owned by ChironAI. This extension only requests start/stop/update
through host_context.hermes_runtime.
"""

from __future__ import annotations

from typing import Any

INSTALL_URL = "https://hermes-agent.nousresearch.com/"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8642/health"
DEFAULT_DASHBOARD_URL = "http://127.0.0.1:9119/"


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


def _tab_order(manifest: Any, fallback: int) -> int:
    tab_ui = _manifest_tab_ui(manifest)
    try:
        return int(tab_ui.get("order") or fallback)
    except Exception:
        return fallback


class HermesAgentExtension:
    def __init__(self, host_context: Any, manifest: Any) -> None:
        self._host = host_context
        self._manifest = manifest

    def _runtime(self) -> Any | None:
        runtime = getattr(self._host, "hermes_runtime", None)
        if runtime is not None:
            return runtime
        metadata = getattr(self._host, "metadata", {}) or {}
        if isinstance(metadata, dict):
            return metadata.get("hermes_runtime")
        return None

    def _unavailable(self) -> dict[str, Any]:
        return {
            "ok": False,
            "installed": False,
            "running": False,
            "tone": "error",
            "message": "Hermes runtime is unavailable",
            "health_url": DEFAULT_HEALTH_URL,
            "dashboard_url": DEFAULT_DASHBOARD_URL,
            "install_url": INSTALL_URL,
            "binary": "",
            "version": "",
            "pid": None,
            "processes": [
                {"id": "gateway", "label": "Gateway", "alive": False, "pid": None, "rss_bytes": 0, "rss": ""},
                {"id": "dashboard", "label": "Dashboard", "alive": False, "pid": None, "rss_bytes": 0, "rss": ""},
            ],
            "rss_bytes": 0,
            "rss": "",
            "login_autostart": False,
            "http_status": None,
            "home": "",
            "default_model": "",
            "image_gen": "",
            "plugins": "",
        }

    def _status(self) -> dict[str, Any]:
        runtime = self._runtime()
        if runtime is None:
            return self._unavailable()
        inspect = getattr(runtime, "inspect", None)
        if not callable(inspect):
            return self._unavailable()
        try:
            status = dict(inspect() or {})
        except Exception as exc:
            unavailable = self._unavailable()
            unavailable["message"] = str(exc)
            return unavailable
        status.setdefault("health_url", DEFAULT_HEALTH_URL)
        status.setdefault("dashboard_url", DEFAULT_DASHBOARD_URL)
        status.setdefault("install_url", INSTALL_URL)
        status.setdefault("tone", "neutral")
        return status

    def _runtime_status_tile(self, status: dict[str, Any]) -> dict[str, Any]:
        running = bool(status.get("running"))
        message = str(status.get("message") or "").strip()
        tone = str(status.get("tone") or "neutral").strip().lower() or "neutral"
        if tone not in {"neutral", "success", "warning", "error", "info"}:
            tone = "neutral"
        label = message or ("running" if running else "stopped")
        return {"tone": tone, "label": label}

    def _process_rows(self, status: dict[str, Any]) -> list[dict[str, Any]]:
        by_id = {
            str(item.get("id") or ""): dict(item)
            for item in (status.get("processes") or [])
            if isinstance(item, dict)
        }
        rows: list[dict[str, Any]] = []
        for role_id, label in (("gateway", "Gateway"), ("dashboard", "Dashboard")):
            proc = by_id.get(role_id) or {"id": role_id, "label": label, "alive": False}
            proc.setdefault("label", label)
            rows.append(proc)
        return rows

    def _process_status_tile(self, proc: dict[str, Any]) -> dict[str, Any]:
        if not proc.get("alive"):
            return {"tone": "error", "label": "dead"}
        parts = ["alive"]
        if proc.get("pid") is not None:
            parts.append(f"PID {proc.get('pid')}")
        rss = str(proc.get("rss") or "").strip()
        if rss:
            parts.append(rss)
        return {"tone": "success", "label": " · ".join(parts)}

    def get_tab_descriptor(self, *, runtime: Any | None = None) -> dict[str, Any]:
        status = self._status()
        return {
            "id": "hermes-agent",
            "title": _tab_title(self._manifest, "Hermes"),
            "icon": _tab_icon(self._manifest, "icons/hermes-agent-light.svg"),
            "description": "Host-managed Hermes Agent gateway.",
            "frame": {},
            "order": _tab_order(self._manifest, 62),
            "status": status,
        }

    def get_tab_payload(self, *, runtime: Any | None = None) -> dict[str, Any]:
        status = self._status()
        running = bool(status.get("running"))
        installed = bool(status.get("installed"))
        actions = [
            {
                "id": "refresh",
                "label": "Refresh",
                "variant": "secondary",
                "icon": "refresh",
            }
        ]
        if installed:
            actions.append(
                {
                    "id": "update",
                    "label": "Update Hermes",
                    "variant": "secondary",
                    "icon": "system_update",
                }
            )
        if running:
            actions.append(
                {
                    "id": "stop",
                    "label": "Stop service",
                    "variant": "danger",
                    "icon": "stop_circle",
                    "confirm": "Stop the Hermes Agent gateway?",
                }
            )
        else:
            actions.append(
                {
                    "id": "start",
                    "label": "Start service",
                    "variant": "primary",
                    "icon": "play_circle",
                    "disabled": not installed,
                }
            )
        actions.append(
            {
                "id": "open_external",
                "label": "Open external",
                "variant": "default",
                "icon": "open_in_new",
            }
        )

        dashboard_url = str(status.get("dashboard_url") or DEFAULT_DASHBOARD_URL)
        processes = self._process_rows(status)
        ram_total = str(status.get("rss") or "").strip()
        if not ram_total:
            ram_bytes = sum(int(item.get("rss_bytes") or 0) for item in processes)
            ram_total = f"{ram_bytes} B" if ram_bytes else "—"
        details = [
            {"label": "Home", "value": str(status.get("home") or "")},
            {"label": "Binary", "value": str(status.get("binary") or "") or "not installed"},
            {"label": "Status", "value": self._runtime_status_tile(status)},
            *[
                {"label": str(item.get("label") or item.get("id") or "Process"), "value": self._process_status_tile(item)}
                for item in processes
            ],
            {"label": "RAM total", "value": ram_total},
            {"label": "Health URL", "value": str(status.get("health_url") or DEFAULT_HEALTH_URL)},
            {"label": "Dashboard URL", "value": dashboard_url},
            {"label": "Default model", "value": str(status.get("default_model") or "")},
            {"label": "Image gen", "value": str(status.get("image_gen") or "")},
            {"label": "Plugins", "value": str(status.get("plugins") or "")},
            {"label": "Version", "value": str(status.get("version") or "")},
            {
                "label": "Login autostart",
                "value": "enabled" if status.get("login_autostart") else "disabled",
            },
            {"label": "Install", "value": str(status.get("install_url") or INSTALL_URL)},
        ]

        schema_actions = [
            {
                "type": "action",
                "action_id": action["id"],
                "label": action.get("label"),
                "variant": action.get("variant"),
                "confirm": action.get("confirm"),
            }
            for action in actions
        ]

        return {
            "title": _tab_title(self._manifest, "Hermes"),
            "icon": _tab_icon(self._manifest, "icons/hermes-agent-light.svg"),
            "frame": {},
            "status": status,
            "content": {
                "type": "service_panel",
                "title": _tab_title(self._manifest, "Hermes"),
                "subtitle": "Host-managed Hermes Agent gateway",
                "open_external_url": dashboard_url,
                "fields": [],
                "actions": actions,
                "details": details,
                "service": {
                    "name": _tab_title(self._manifest, "Hermes"),
                    "subtitle": "Host-managed Hermes Agent gateway",
                    "icon": "smart_toy",
                    "httpStatus": f"HTTP {status.get('http_status')}" if status.get("http_status") else "",
                    "status": self._runtime_status_tile(status),
                    "fieldKey": "",
                    "metaColumns": 2,
                    "actions": actions,
                    "meta": details,
                },
            },
            "schema": {
                "pages": [
                    {
                        "id": "hermes-agent-settings",
                        "sections": [
                            {
                                "id": "hermes-agent-actions",
                                "title": "Hermes Agent",
                                "components": [
                                    {
                                        "type": "status",
                                        "key": "status",
                                        "label": "Service",
                                        "status": "running" if running else "stopped" if installed else "missing",
                                        "message": str(status.get("message") or ""),
                                    },
                                    *schema_actions,
                                    {
                                        "type": "text",
                                        "key": "details",
                                        "label": "Details",
                                        "value": (
                                            f"Binary={status.get('binary') or 'not installed'} | "
                                            f"Gateway={'alive' if processes[0].get('alive') else 'dead'} | "
                                            f"Dashboard={'alive' if processes[1].get('alive') else 'dead'} | "
                                            f"RAM={status.get('rss') or '—'} | "
                                            f"Health URL={status.get('health_url') or DEFAULT_HEALTH_URL} | "
                                            f"Dashboard URL={status.get('dashboard_url') or DEFAULT_DASHBOARD_URL} | "
                                            f"Version={status.get('version') or ''} | "
                                            f"Install={status.get('install_url') or INSTALL_URL}"
                                        ),
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        }

    def run_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        *,
        runtime: Any | None = None,
    ) -> dict[str, Any]:
        action = str(action_id or "").strip()
        hermes = self._runtime()
        if hermes is None:
            unavailable = self._unavailable()
            return {"ok": False, "message": unavailable["message"], "status": unavailable}
        if action == "refresh":
            return {"ok": True, "message": "Refreshed", "status": self._status()}
        if action == "start":
            result = dict(hermes.ensure() or {})
            result["status"] = result.get("status") or self._status()
            return result
        if action == "stop":
            result = dict(hermes.stop() or {})
            result["status"] = result.get("status") or self._status()
            return result
        if action == "update":
            result = dict(hermes.update() or {})
            result["status"] = result.get("status") or self._status()
            return result
        if action == "open_external":
            url = DEFAULT_DASHBOARD_URL
            status: dict[str, Any] = {}
            ensure_dashboard = getattr(hermes, "ensure_dashboard", None)
            if callable(ensure_dashboard):
                try:
                    result = dict(ensure_dashboard(open_browser=True) or {})
                except TypeError:
                    result = dict(ensure_dashboard() or {})
                except Exception as exc:
                    status = self._status()
                    url = str(status.get("dashboard_url") or url)
                    return {
                        "ok": True,
                        "message": url,
                        "open_external_url": url,
                        "status": status,
                        "warning": str(exc),
                    }
                status = result.get("status") or self._status()
                url = str(result.get("dashboard_url") or status.get("dashboard_url") or url)
            else:
                status = self._status()
                url = str(status.get("dashboard_url") or url)
            return {"ok": True, "message": url, "open_external_url": url, "status": status}
        raise ValueError(f"Unsupported action: {action}")


def create_provider(host_context: Any, manifest: Any) -> HermesAgentExtension:
    return HermesAgentExtension(host_context, manifest)
