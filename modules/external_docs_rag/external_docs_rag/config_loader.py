"""
Load external_sources and rag_sources from YAML config.
"""

from __future__ import annotations

import os
from pathlib import Path

from external_docs_rag.domain.entities import ExternalSource, RagSourceConfig

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def load_external_sources(config_path: str | None = None) -> list[ExternalSource]:
    """Load external_sources list from YAML. Default: module_dir/../config/sources.yaml."""
    if not _HAS_YAML:
        return []
    path = config_path or os.path.join(_module_dir(), "..", "config", "sources.yaml")
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw = data.get("external_sources") or []
    out: list[ExternalSource] = []
    for r in raw:
        if isinstance(r, dict) and r.get("id") and r.get("base_url") and r.get("paths"):
            out.append(ExternalSource(
                id=str(r["id"]),
                base_url=str(r["base_url"]),
                paths=[str(p) for p in r["paths"]],
                collection_name=str(r.get("collection_name", r["id"])),
                top_k=int(r.get("top_k", 2)),
            ))
    return out


def load_rag_sources_config(config_path: str | None = None) -> list[RagSourceConfig]:
    """Load rag_sources list from YAML (collection_name, top_k, trigger_keywords, label)."""
    if not _HAS_YAML:
        return []
    path = config_path or os.path.join(_module_dir(), "..", "config", "sources.yaml")
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    raw = data.get("rag_sources") or []
    out: list[RagSourceConfig] = []
    for r in raw:
        if isinstance(r, dict) and r.get("collection_name") is not None:
            out.append(RagSourceConfig(
                collection_name=str(r["collection_name"]),
                top_k=int(r.get("top_k", 6)),
                trigger_keywords=[str(k) for k in (r.get("trigger_keywords") or [])],
                label=str(r.get("label", "")),
                on_demand_fetch=bool(r.get("on_demand_fetch", False)),
                external_source_id=str(r.get("external_source_id", "")),
            ))
    return out


__all__ = ["load_external_sources", "load_rag_sources_config"]
