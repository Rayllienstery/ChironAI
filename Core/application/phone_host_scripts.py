"""Catalog and enable/disable flags for iPhone phone-host scripts."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

PHONE_HOST_SCRIPTS_SETTING = "phone_host_scripts_enabled"

PHONE_HOST_SCRIPT_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "phone-host",
        "file": "phone-host.ps1",
        "wrapper": "phone-host.cmd",
        "title": "Phone host",
        "description": "iPhone Shortcut SSH entry: status, sleep, and router wake help.",
    },
    {
        "id": "setup-openssh",
        "file": "setup-openssh.ps1",
        "wrapper": "",
        "title": "OpenSSH setup",
        "description": "Installs OpenSSH Server and the dedicated iPhone key.",
    },
)


def phone_host_repo_root() -> Path:
    override = (os.getenv("CHIRONAI_REPO_ROOT") or os.getenv("REPO_ROOT") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def phone_host_scripts_dir() -> Path:
    return phone_host_repo_root() / "scripts" / "phone_host"


def phone_host_enabled_path() -> Path:
    return phone_host_scripts_dir() / "enabled.json"


def _parse_enabled_map(raw: Any) -> dict[str, bool]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    for key, value in raw.items():
        script_id = str(key or "").strip()
        if not script_id:
            continue
        out[script_id] = bool(value)
    return out


def _known_ids() -> set[str]:
    return {str(row["id"]) for row in PHONE_HOST_SCRIPT_CATALOG}


def load_phone_host_enabled_map(settings_repo: Any | None = None) -> dict[str, bool]:
    merged = {script_id: True for script_id in _known_ids()}
    path = phone_host_enabled_path()
    try:
        if path.is_file():
            merged.update(_parse_enabled_map(path.read_text(encoding="utf-8")))
    except OSError:
        pass
    if settings_repo is not None:
        with suppress(Exception):
            merged.update(_parse_enabled_map(settings_repo.get_app_setting(PHONE_HOST_SCRIPTS_SETTING)))
    return {script_id: bool(merged.get(script_id, True)) for script_id in _known_ids()}


def save_phone_host_enabled_map(enabled: dict[str, bool], settings_repo: Any | None = None) -> dict[str, bool]:
    known = _known_ids()
    payload = {script_id: bool(enabled.get(script_id, True)) for script_id in known}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = phone_host_enabled_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if settings_repo is not None:
        with suppress(Exception):
            settings_repo.set_app_setting(PHONE_HOST_SCRIPTS_SETTING, json.dumps(payload, sort_keys=True))
    return payload


def list_phone_host_scripts(settings_repo: Any | None = None) -> list[dict[str, Any]]:
    enabled = load_phone_host_enabled_map(settings_repo)
    root = phone_host_scripts_dir()
    rows: list[dict[str, Any]] = []
    for spec in PHONE_HOST_SCRIPT_CATALOG:
        script_id = spec["id"]
        file_name = spec["file"]
        wrapper = spec.get("wrapper") or ""
        path = root / file_name
        wrapper_path = root / wrapper if wrapper else None
        rows.append(
            {
                "id": script_id,
                "file": file_name,
                "wrapper": wrapper or None,
                "path": str(Path("scripts") / "phone_host" / file_name),
                "title": spec["title"],
                "description": spec["description"],
                "enabled": bool(enabled.get(script_id, True)),
                "exists": path.is_file(),
                "wrapper_exists": bool(wrapper_path and wrapper_path.is_file()),
            }
        )
    return rows


def set_phone_host_script_enabled(
    script_id: str,
    enabled: bool,
    settings_repo: Any | None = None,
) -> list[dict[str, Any]]:
    wanted = str(script_id or "").strip()
    if wanted not in _known_ids():
        raise KeyError(wanted)
    current = load_phone_host_enabled_map(settings_repo)
    current[wanted] = bool(enabled)
    save_phone_host_enabled_map(current, settings_repo)
    return list_phone_host_scripts(settings_repo)
