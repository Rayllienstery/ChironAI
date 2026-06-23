"""Message catalog loader and ``t()`` helper."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
SUPPORTED_LOCALES = ("en", "en-XA", "ru")


def available_locales() -> tuple[str, ...]:
    """Return locales that are registered and have a catalog directory."""
    return tuple(locale for locale in SUPPORTED_LOCALES if (_CATALOG_DIR / locale).is_dir())


@lru_cache(maxsize=8)
def load_catalog(locale: str = "en") -> dict[str, str]:
    if locale not in SUPPORTED_LOCALES:
        return {}
    path = _CATALOG_DIR / locale / "common.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def t(message_id: str, *, locale: str = "en", **kwargs: object) -> str:
    """Resolve a message id from the catalog; supports ``{placeholder}`` formatting."""
    catalog = load_catalog(locale)
    template = catalog.get(message_id, message_id)
    if kwargs:
        try:
            return str(template).format(**kwargs)
        except (KeyError, ValueError):
            return str(template)
    return str(template)


__all__ = ["SUPPORTED_LOCALES", "available_locales", "load_catalog", "t"]
