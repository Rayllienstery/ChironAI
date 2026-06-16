"""Load and persist crawler sources.yaml for WebUI routes."""

from __future__ import annotations

import logging
import os

_WEBUI_LOG = logging.getLogger("webui")


def _sources_config_path(root: str) -> str:
    core_config = os.path.join(root, "Core", "config", "sources.yaml")
    if os.path.isfile(core_config):
        return core_config
    return os.path.join(root, "config", "sources.yaml")


def load_sources_config(root: str) -> list[dict]:
    """Load sources from config/sources.yaml."""
    try:
        import yaml

        config_path = _sources_config_path(root)
        if not os.path.isfile(config_path):
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data.get("sources", [])
    except Exception as e:
        _WEBUI_LOG.warning(f"Failed to load sources config: {e}")
        return []


def save_sources_config(root: str, sources: list[dict]) -> bool:
    """Save sources to config/sources.yaml. Returns True on success."""
    try:
        import yaml

        config_path = _sources_config_path(root)
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)

        data = {"sources": sources}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return True
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to save sources config: {e}")
        return False


__all__ = ["load_sources_config", "save_sources_config"]
