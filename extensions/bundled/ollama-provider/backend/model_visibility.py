"""
Ollama hidden-model list for the ollama-provider extension.

Self-contained: persistence is via a settings_repository passed explicitly
(obtained from host_context.get_settings_repository()).
No imports from infrastructure.* or domain.*.
"""

from __future__ import annotations

import json
from typing import Any

_APP_KEY = "ollama_hidden_model_ids"
_MAX_ID_LEN = 512


def _normalize(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or len(s) > _MAX_ID_LEN:
        return None
    if any(c in s for c in "\n\r\x00"):
        return None
    return s


def get_hidden_ollama_model_ids(settings_repo: Any) -> frozenset[str]:
    raw = settings_repo.get_app_setting(_APP_KEY)
    if not raw or not raw.strip():
        return frozenset()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    out: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        n = _normalize(item)
        if n:
            out.add(n)
    return frozenset(out)


def _save_hidden(settings_repo: Any, ids: frozenset[str]) -> list[str]:
    ordered = sorted(ids)
    settings_repo.set_app_setting(_APP_KEY, json.dumps(ordered))
    return ordered


def patch_hidden_ollama_model_ids(
    settings_repo: Any,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[str]:
    cur = set(get_hidden_ollama_model_ids(settings_repo))
    for a in add or []:
        if isinstance(a, str):
            n = _normalize(a)
            if n:
                cur.add(n)
    for r in remove or []:
        if isinstance(r, str):
            n = _normalize(r)
            if n:
                cur.discard(n)
    return _save_hidden(settings_repo, frozenset(cur))


def _entry_name(entry: dict[str, Any]) -> str | None:
    if not isinstance(entry, dict):
        return None
    return _normalize((entry.get("name") or entry.get("model") or ""))


def filter_ollama_tag_entries_for_editors(
    entries: list[dict[str, Any]],
    hidden: frozenset[str],
) -> list[dict[str, Any]]:
    """Keep tag dicts whose model name is not in ``hidden``."""
    out: list[dict[str, Any]] = []
    for m in entries:
        if not isinstance(m, dict):
            continue
        name = _entry_name(m)
        if not name or name in hidden:
            continue
        out.append(m)
    return out


__all__ = [
    "filter_ollama_tag_entries_for_editors",
    "get_hidden_ollama_model_ids",
    "patch_hidden_ollama_model_ids",
]
