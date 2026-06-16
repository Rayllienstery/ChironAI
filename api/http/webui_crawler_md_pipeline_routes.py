"""Markdown pipeline admin routes for the crawler."""

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

try:
    from modules.md_indexer import (
        delete_pipeline as md_indexer_delete_pipeline,
        get_active_pipeline_name,
        list_pipeline_names,
        load_pipeline,
        run_pipeline,
        save_pipeline,
    )
except ImportError:
    md_indexer_delete_pipeline = None  # type: ignore[assignment]
    get_active_pipeline_name = None  # type: ignore[assignment]
    list_pipeline_names = None  # type: ignore[assignment]
    load_pipeline = None  # type: ignore[assignment]
    run_pipeline = None  # type: ignore[assignment]
    save_pipeline = None  # type: ignore[assignment]

_ERROR_LOG: Any = None


def register_crawler_md_pipeline_routes(
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

    # ---- MD Pipelines (config-driven markdown cleanup) ----

    @bp.route("/crawler/md-pipelines", methods=["GET"])
    def get_md_pipelines_list() -> Any:
        """List available pipeline names (config/md_pipelines/*.json)."""
        if list_pipeline_names is None:
            return _error_response("md_indexer module not available", 500)
        try:
            names = list_pipeline_names()
            return jsonify({"pipelines": names})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_md_pipelines_list", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["GET"])
    def get_md_pipeline(name: str) -> Any:
        """Get pipeline JSON by name."""
        if load_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            pipeline = load_pipeline(name)
            if pipeline is None:
                return _error_response(f"Pipeline '{name}' not found", 404)
            return jsonify(pipeline.to_dict())
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["PUT", "POST"])
    def save_md_pipeline(name: str) -> Any:
        """Save pipeline JSON by name. Body: { "name": "...", "steps": [...] }."""
        if save_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            body = request.get_json(force=True, silent=True) or {}
            if "steps" not in body:
                return _error_response("Missing 'steps' in body", 400)
            from modules.md_indexer.domain.schema import Pipeline
            pipeline = Pipeline.from_dict(body)
            save_pipeline(name, pipeline)
            return jsonify({"ok": True, "name": name})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.save_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/<name>", methods=["DELETE"])
    def delete_md_pipeline(name: str) -> Any:
        """Delete pipeline by name."""
        if md_indexer_delete_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            if md_indexer_delete_pipeline(name):
                return jsonify({"ok": True, "name": name})
            return _error_response(f"Pipeline '{name}' not found", 404)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.delete_md_pipeline", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/md-pipelines/preview", methods=["POST"])
    def preview_md_pipeline() -> Any:
        """Run a pipeline on a source file and return source_md + processed_md."""
        if run_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        try:
            body = request.get_json(force=True, silent=True) or {}
            pipeline_name = body.get("pipeline_name")
            pipeline_definition = body.get("pipeline")
            source_id = body.get("source_id")
            filename = body.get("filename")
            if not source_id or not filename:
                return _error_response("Missing source_id or filename", 400)
            sources_dir = get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                return _error_response("Invalid filename", 400)
            basename = os.path.basename(requested_path)
            if not basename.lower().endswith(".md"):
                return _error_response("Only .md files are supported", 400)
            if not os.path.isfile(requested_path):
                return _error_response("File not found", 404)
            with open(requested_path, "r", encoding="utf-8") as f:
                source_md = f.read()
            pipeline_to_run = pipeline_definition if isinstance(pipeline_definition, dict) else pipeline_name
            if pipeline_to_run is None and get_active_pipeline_name is not None:
                pipeline_to_run = get_active_pipeline_name()
            page_meta, processed_md = run_pipeline(pipeline_to_run, source_md)
            return jsonify({
                "source_id": source_id,
                "filename": basename,
                "page_meta": page_meta,
                "source_md": source_md,
                "processed_md": processed_md,
            })
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.preview_md_pipeline", exc_info=True)
            return _error_response(e)




__all__ = ["register_crawler_md_pipeline_routes"]
