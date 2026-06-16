"""Load/save WebUI/rag_sources/*/meta.json and index bookkeeping (chunk_hashes)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from webui_backend.paths import webui_data_dir

_LOG = logging.getLogger("webui")


def rag_sources_dir() -> str:
    return str(webui_data_dir() / "rag_sources")


def load_source_meta(source_id: str) -> dict[str, Any] | None:
    meta_path = os.path.join(rag_sources_dir(), source_id, "meta.json")
    if not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("source_id", source_id)
        data.setdefault("source_url", "")
        data.setdefault("last_crawled", None)
        data.setdefault("hash_algo", "sha256")
        data.setdefault("pages", {})
        return data
    except Exception as e:
        _LOG.warning("Failed to load meta.json for %s: %s", source_id, e)
        return None


def save_source_meta(source_id: str, meta: dict[str, Any]) -> None:
    root = os.path.join(rag_sources_dir(), source_id)
    os.makedirs(root, exist_ok=True)
    meta_path = os.path.join(root, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def update_page_chunk_hashes(source_id: str, filename: str, chunk_hashes: list[str]) -> None:
    """Persist chunk_hashes for a page after successful index upsert."""
    meta = load_source_meta(source_id)
    if meta is None:
        return
    pages = meta.setdefault("pages", {})
    entry = pages.setdefault(filename, {})
    if not isinstance(entry, dict):
        entry = {}
        pages[filename] = entry
    entry["chunk_hashes"] = list(chunk_hashes)
    save_source_meta(source_id, meta)


def clear_chunk_hashes_for_sources(source_ids: list[str]) -> int:
    """Remove chunk_hashes from every page in the given sources. Returns pages cleared."""
    cleared = 0
    for source_id in source_ids:
        meta = load_source_meta(source_id)
        if not meta:
            continue
        pages = meta.get("pages") or {}
        changed = False
        for entry in pages.values():
            if isinstance(entry, dict) and entry.pop("chunk_hashes", None) is not None:
                changed = True
                cleared += 1
        if changed:
            save_source_meta(source_id, meta)
    return cleared


def parse_source_ids_from_framework_id(framework_id: str | None) -> list[str]:
    if not framework_id:
        return []
    return [s.strip() for s in str(framework_id).split(",") if s.strip()]


__all__ = [
    "clear_chunk_hashes_for_sources",
    "load_source_meta",
    "parse_source_ids_from_framework_id",
    "rag_sources_dir",
    "save_source_meta",
    "update_page_chunk_hashes",
]
