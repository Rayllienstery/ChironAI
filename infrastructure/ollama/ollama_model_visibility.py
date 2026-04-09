"""App-level hidden Ollama model ids (deny-list for editor dropdowns; Ollama has no native hide)."""

from __future__ import annotations

import json
from typing import Any

from infrastructure.database import get_settings_repository

_APP_KEY = "ollama_hidden_model_ids"
_MAX_ID_LEN = 512


def normalize_ollama_model_id(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or len(s) > _MAX_ID_LEN:
        return None
    if any(c in s for c in "\n\r\x00"):
        return None
    return s


def get_hidden_ollama_model_ids() -> frozenset[str]:
    repo = get_settings_repository()
    raw = repo.get_app_setting(_APP_KEY)
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
        n = normalize_ollama_model_id(item)
        if n:
            out.add(n)
    return frozenset(out)


def _save_hidden(ids: frozenset[str]) -> list[str]:
    ordered = sorted(ids)
    get_settings_repository().set_app_setting(_APP_KEY, json.dumps(ordered))
    return ordered


def set_hidden_ollama_model_ids(ids: list[str]) -> list[str]:
    normalized: set[str] = set()
    for x in ids:
        n = normalize_ollama_model_id(x) if isinstance(x, str) else None
        if n:
            normalized.add(n)
    return _save_hidden(frozenset(normalized))


def patch_hidden_ollama_model_ids(*, add: list[str] | None = None, remove: list[str] | None = None) -> list[str]:
    cur = set(get_hidden_ollama_model_ids())
    for a in add or []:
        if isinstance(a, str):
            n = normalize_ollama_model_id(a)
            if n:
                cur.add(n)
    for r in remove or []:
        if isinstance(r, str):
            n = normalize_ollama_model_id(r)
            if n:
                cur.discard(n)
    return _save_hidden(frozenset(cur))


def ollama_tag_entry_name(entry: dict[str, Any]) -> str | None:
    if not isinstance(entry, dict):
        return None
    return normalize_ollama_model_id((entry.get("name") or entry.get("model") or ""))


def filter_ollama_tag_entries_for_editors(
    entries: list[dict[str, Any]],
    hidden: frozenset[str],
) -> list[dict[str, Any]]:
    """Keep tag dicts whose model name is not in ``hidden``."""
    out: list[dict[str, Any]] = []
    for m in entries:
        if not isinstance(m, dict):
            continue
        name = ollama_tag_entry_name(m)
        if not name or name in hidden:
            continue
        out.append(m)
    return out
