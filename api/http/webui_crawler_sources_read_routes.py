"""Crawler source read routes (list, detail, pages, stats)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Callable

from error_manager.http import error_response as _error_response
from flask import jsonify, request
from typing import Callable

from api.http.webui_crawler_helpers import compute_source_stats, discover_crawler_sources

_ERROR_LOG: Any = None


def register_crawler_sources_read_routes(
    bp,
    *,
    error_log,
    root: str,
    webui_backend: str,
    get_crawler_sources_dir: Callable[[], str],
    load_source_meta: Callable[[str], dict | None],
    load_sources_config: Callable[[], list[dict]],
    save_sources_config: Callable[[list[dict]], bool],
) -> None:
    global _ERROR_LOG
    _ERROR_LOG = error_log
    _ROOT = root
    _WEBUI_BACKEND = webui_backend

    @bp.route("/crawler/sources", methods=["GET"])
    def get_crawler_sources() -> Any:
        """Get list of all configured crawl sources with metadata."""
        try:
            # Load sources from config/sources.yaml
            config_sources = load_sources_config()
            config_sources_dict = {s.get("id"): s for s in config_sources}
    
            discovered_ids = set(discover_crawler_sources())
            sources = []

            for source_id in sorted(discovered_ids):
                meta = load_source_meta(source_id)
                if not meta:
                    continue

                stats = compute_source_stats(meta)
                source_data = {
                    "id": source_id,
                    "url": meta.get("source_url", ""),
                    "last_crawled": meta.get("last_crawled"),
                    "total_pages": stats["total_pages"],
                    "indexed_pages": stats["indexed_pages"],
                    "has_meta": True,
                }

                # Get config from sources.yaml if available, otherwise from meta
                config_source = config_sources_dict.get(source_id)
                if config_source:
                    source_data["url"] = config_source.get("url", source_data["url"])
                    source_data["max_depth"] = config_source.get("max_depth", 2)
                    source_data["crawler"] = config_source.get("crawler", "playwright")
                    source_data["doc_only"] = config_source.get("doc_only", True)
                    source_data["seed_urls"] = config_source.get("seed_urls", [])
                else:
                    # Fallback to meta.json
                    if "max_depth" in meta:
                        source_data["max_depth"] = meta["max_depth"]
                    if "crawler" in meta:
                        source_data["crawler"] = meta["crawler"]
                    if "doc_only" in meta:
                        source_data["doc_only"] = meta["doc_only"]
                    if "seed_urls" in meta:
                        source_data["seed_urls"] = meta["seed_urls"]

                sources.append(source_data)

            # Include sources from config that are not yet discovered (no rag_sources/<id>/meta.json)
            for config_source in config_sources:
                cid = config_source.get("id")
                if not cid or cid in discovered_ids:
                    continue
                source_data = {
                    "id": cid,
                    "url": config_source.get("url", ""),
                    "last_crawled": None,
                    "total_pages": 0,
                    "indexed_pages": 0,
                    "has_meta": False,
                    "max_depth": config_source.get("max_depth", 2),
                    "crawler": config_source.get("crawler", "playwright"),
                    "doc_only": config_source.get("doc_only", True),
                    "seed_urls": config_source.get("seed_urls", []),
                }
                sources.append(source_data)

            # Keep stable order: discovered first (sorted), then config-only (by id)
            sources.sort(key=lambda s: (s["id"],))

            return jsonify({"sources": sources})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_sources", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>", methods=["GET"])
    def get_crawler_source(source_id: str) -> Any:
        """Get detailed configuration for a specific source."""
        try:
            # Load from config/sources.yaml
            sources = load_sources_config()
            source = next((s for s in sources if s.get("id") == source_id), None)
    
            if not source:
                # Fallback to meta.json
                meta = load_source_meta(source_id)
                if not meta:
                    return _error_response("Source not found", 404)
        
                source = {
                    "id": source_id,
                    "url": meta.get("source_url", ""),
                    "max_depth": meta.get("max_depth", 2),
                    "crawler": meta.get("crawler", "playwright"),
                    "doc_only": meta.get("doc_only", True),
                    "seed_urls": meta.get("seed_urls", []),
                }
    
            return jsonify(source)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>/pages", methods=["GET"])
    def get_crawler_source_pages(source_id: str) -> Any:
        """Get detailed page list for a source."""
        try:
            meta = load_source_meta(source_id)
            if not meta:
                return _error_response("Source not found", 404)
    
            pages = meta.get("pages", {})
            page_list = []
            for filename, page_data in pages.items():
                page_list.append({
                    "filename": filename,
                    "url": page_data.get("url", ""),
                    "last_updated": page_data.get("last_updated"),
                    "has_chunks": bool(page_data.get("chunk_hashes")),
                    "chunk_count": len(page_data.get("chunk_hashes", [])),
                })
    
            # Sort by last_updated descending
            page_list.sort(key=lambda x: x["last_updated"] or "", reverse=True)
    
            return jsonify({
                "source_id": source_id,
                "pages": page_list,
                "total": len(page_list),
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source_pages", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/sources/<source_id>/stats", methods=["GET"])
    def get_crawler_source_stats(source_id: str) -> Any:
        """Get statistics for a source."""
        try:
            meta = load_source_meta(source_id)
            if not meta:
                return _error_response("Source not found", 404)
    
            stats = compute_source_stats(meta)
            return jsonify({
                "source_id": source_id,
                **stats,
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_crawler_source_stats", exc_info=True)
            return _error_response(e)




__all__ = ["register_crawler_sources_read_routes"]
