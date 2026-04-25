"""Persisted extension install state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

INSTALL_STATE_APP_KEY = "extensions_install_state_v1"


@dataclass(frozen=True)
class InstalledExtensionRecord:
    id: str
    version: str
    enabled: bool = True
    installed: bool = True
    source: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    description: str = ""
    icon: str = ""
    restart_required: bool = False


class ExtensionsRepository:
    """Persisted install state stored in app settings."""

    def __init__(self, settings_repo: Any) -> None:
        self._settings_repo = settings_repo

    def list_records(self) -> list[InstalledExtensionRecord]:
        raw = self._settings_repo.get_app_setting(INSTALL_STATE_APP_KEY)
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        out: list[InstalledExtensionRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ext_id = str(item.get("id") or "").strip()
            version = str(item.get("version") or "").strip()
            if not ext_id or not version:
                continue
            out.append(
                InstalledExtensionRecord(
                    id=ext_id,
                    version=version,
                    enabled=bool(item.get("enabled", True)),
                    installed=bool(item.get("installed", True)),
                    source=dict(item.get("source") or {}),
                    title=str(item.get("title") or ""),
                    description=str(item.get("description") or ""),
                    icon=str(item.get("icon") or ""),
                    restart_required=bool(item.get("restart_required", False)),
                )
            )
        return out

    def save_records(self, records: list[InstalledExtensionRecord]) -> None:
        payload = [
            {
                "id": record.id,
                "version": record.version,
                "enabled": bool(record.enabled),
                "installed": bool(record.installed),
                "source": dict(record.source or {}),
                "title": record.title,
                "description": record.description,
                "icon": record.icon,
                "restart_required": bool(record.restart_required),
            }
            for record in records
        ]
        self._settings_repo.set_app_setting(INSTALL_STATE_APP_KEY, json.dumps(payload))
