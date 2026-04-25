"""Registry discovery for extension catalogs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_REGISTRY_PATH = "extensions/registry/extensions.json"


class ExtensionRegistryClient:
    """Loads an extension registry from file or URL."""

    def __init__(self, registry_url: str | None = None, *, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self._registry_url = registry_url or self._default_registry_url()

    def _default_registry_url(self) -> str:
        return str((self._project_root / DEFAULT_REGISTRY_PATH).resolve())

    @property
    def registry_url(self) -> str:
        return self._registry_url

    def load(self) -> list[dict[str, Any]]:
        raw = self._load_json_obj(self._registry_url)
        if isinstance(raw, dict) and isinstance(raw.get("extensions"), list):
            raw = raw["extensions"]
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict) and str(item.get("id") or "").strip():
                out.append(dict(item))
        return out

    def _load_json_obj(self, location: str) -> Any:
        parsed = urlparse(location)
        if parsed.scheme in ("http", "https"):
            resp = requests.get(location, timeout=30)
            resp.raise_for_status()
            return resp.json()
        if parsed.scheme == "file":
            path = Path(parsed.path)
        else:
            path = Path(location)
            if not path.is_absolute():
                path = (self._project_root / path).resolve()
        return json.loads(path.read_text(encoding="utf-8"))
