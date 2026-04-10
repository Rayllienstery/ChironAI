"""Load/save config/sources.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_sources(project_root: Path) -> list[dict[str, Any]]:
    config_path = project_root / "config" / "sources.yaml"
    if not config_path.is_file():
        return _default_sources()
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        sources = data.get("sources", [])
        for source in sources:
            if "seed_urls" not in source:
                source["seed_urls"] = []
            elif not isinstance(source["seed_urls"], list):
                source["seed_urls"] = []
        return sources if sources else _default_sources()
    except Exception:
        return _default_sources()


def _default_sources() -> list[dict[str, Any]]:
    return [
        {
            "id": "apple_documentation",
            "url": "https://developer.apple.com/documentation",
            "max_depth": 2,
            "crawler": "playwright",
            "doc_only": True,
            "seed_urls": [],
        }
    ]


def save_sources(project_root: Path, sources: list[dict[str, Any]]) -> bool:
    config_path = project_root / "config" / "sources.yaml"
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump({"sources": sources}, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except Exception:
        return False
