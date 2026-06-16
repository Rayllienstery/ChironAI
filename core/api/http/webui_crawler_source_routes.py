"""Crawler source admin routes for the WebUI blueprint."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from api.http.webui_crawler_helpers import build_source_meta, is_safe_identifier, normalize_seed_urls


def register_crawler_source_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    get_crawler_sources_dir: Callable[[], str],
    load_source_meta: Callable[[str], dict | None],
    load_sources_config: Callable[[], list[dict]],
    save_sources_config: Callable[[list[dict]], bool],
) -> None:
    @bp.route("/crawler/sources", methods=["POST"])
    def add_crawler_source() -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_id = body.get("id", "").strip()
            url = body.get("url", "").strip()
            max_depth = int(body.get("max_depth", 2))
            crawler = body.get("crawler", "playwright")
            doc_only = bool(body.get("doc_only", True))
            seed_urls = normalize_seed_urls(body.get("seed_urls", []))

            if not source_id:
                return jsonify({"error": "Source ID is required"}), 400
            if not url:
                return jsonify({"error": "URL is required"}), 400
            if not is_safe_identifier(source_id):
                return jsonify({"error": "Source ID must contain only alphanumeric characters, underscores, and hyphens"}), 400

            sources = load_sources_config()
            if any(source.get("id") == source_id for source in sources):
                return jsonify({"error": f"Source '{source_id}' already exists"}), 409

            sources.append(
                {
                    "id": source_id,
                    "url": url,
                    "max_depth": max_depth,
                    "crawler": crawler,
                    "doc_only": doc_only,
                    "seed_urls": seed_urls,
                }
            )
            if not save_sources_config(sources):
                return jsonify({"error": "Failed to save source configuration"}), 500

            sources_dir = get_crawler_sources_dir()
            source_dir = os.path.join(sources_dir, source_id)
            os.makedirs(source_dir, exist_ok=True)

            meta_path = os.path.join(source_dir, "meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    build_source_meta(
                        source_id=source_id,
                        url=url,
                        max_depth=max_depth,
                        crawler=crawler,
                        doc_only=doc_only,
                        seed_urls=seed_urls,
                    ),
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            return jsonify(
                {
                    "status": "created",
                    "source_id": source_id,
                    "message": f"Source '{source_id}' created successfully.",
                }
            )
        except Exception as e:
            error_log.error("webui_routes.add_crawler_source", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/crawler/sources/<source_id>", methods=["PUT"])
    def update_crawler_source(source_id: str) -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            url = body.get("url", "").strip()
            max_depth = int(body.get("max_depth", 2))
            crawler = body.get("crawler", "playwright")
            doc_only = bool(body.get("doc_only", True))
            seed_urls = normalize_seed_urls(body.get("seed_urls", []))

            if not url:
                return jsonify({"error": "URL is required"}), 400

            sources = load_sources_config()
            source_found = False
            for index, source in enumerate(sources):
                if source.get("id") == source_id:
                    sources[index] = {
                        "id": source_id,
                        "url": url,
                        "max_depth": max_depth,
                        "crawler": crawler,
                        "doc_only": doc_only,
                        "seed_urls": seed_urls,
                    }
                    source_found = True
                    break

            if not source_found:
                return jsonify({"error": f"Source '{source_id}' not found"}), 404
            if not save_sources_config(sources):
                return jsonify({"error": "Failed to save source configuration"}), 500

            meta = load_source_meta(source_id)
            if meta:
                meta["source_url"] = url
                meta["max_depth"] = max_depth
                meta["crawler"] = crawler
                meta["doc_only"] = doc_only
                meta["seed_urls"] = seed_urls
                meta_path = os.path.join(get_crawler_sources_dir(), source_id, "meta.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)

            return jsonify(
                {
                    "status": "updated",
                    "source_id": source_id,
                    "message": f"Source '{source_id}' updated successfully.",
                }
            )
        except Exception as e:
            error_log.error("webui_routes.update_crawler_source", exc_info=True)
            return jsonify({"error": str(e)}), 500


__all__ = ["register_crawler_source_routes"]
