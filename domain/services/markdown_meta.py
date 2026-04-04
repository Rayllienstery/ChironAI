"""
Parse and strip the leading <!-- meta ... --> block from Apple doc markdown.

Used at index time: strip the block before chunking (so it is not embedded)
and parse into structured payload (url, framework, doc_kind, availability).
"""

from __future__ import annotations

from typing import Any


def parse_and_strip_meta_block(md: str) -> tuple[dict[str, Any], str]:
    """
    If markdown starts with <!-- ... -->, parse the meta block and remove it.
    Returns (parsed_meta, md_without_block). parsed_meta has: url, framework,
    doc_kind, doc_scope, platforms, availability (dict platform -> version). If no block, returns ({}, md).
    """
    if not md or not md.strip().startswith("<!--"):
        return {}, md

    end_marker = "-->"
    idx = md.find(end_marker)
    if idx == -1:
        return {}, md

    block = md[:idx].strip()
    rest = md[idx + len(end_marker) :].lstrip("\n\r")
    if not block.startswith("<!--"):
        return {}, md
    inner = block[4:].strip()

    meta: dict[str, Any] = {}
    availability: dict[str, str] = {}
    in_availability = False
    for line in inner.splitlines():
        line = line.rstrip()
        if not line:
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("availability:"):
            in_availability = True
            continue
        if in_availability:
            if indent >= 4 and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key:
                    availability[key] = val
            else:
                in_availability = False
        if in_availability:
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().lower().replace("-", "_")
            val = val.strip()
            if key == "url":
                meta["url"] = val
            elif key == "framework":
                meta["framework"] = val
            elif key == "doc_kind":
                meta["doc_kind"] = val
            elif key == "doc_scope":
                meta["doc_scope"] = val
            elif key == "platforms":
                meta["platforms"] = [p.strip() for p in val.split(",") if p.strip()]

    if availability:
        meta["availability"] = availability
        ios_ver = availability.get("iOS") or availability.get("ios")
        swift_ver = availability.get("Swift") or availability.get("swift")
        meta["ios_versions"] = [ios_ver] if ios_ver else []
        meta["swift_versions"] = [swift_ver] if swift_ver else []

    return meta, rest


__all__ = ["parse_and_strip_meta_block"]
