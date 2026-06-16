"""Crawler, source inspection, indexer tester, and collection routes."""

from __future__ import annotations

from typing import Any

from flask import Blueprint

from api.http.webui_crawler_indexing_helpers import (
    clip_text_for_embedding as _clip_text_for_embedding,
    is_embed_context_length_error as _is_embed_context_length_error,
)
from api.http.webui_crawler_helpers import get_crawler_sources_dir, load_source_meta
from api.http.webui_crawler_indexer_routes import register_crawler_indexer_routes
from api.http.webui_crawler_job_routes import register_crawler_job_routes
from api.http.webui_crawler_md_pipeline_routes import register_crawler_md_pipeline_routes
from api.http.webui_crawler_source_config import load_sources_config, save_sources_config
from api.http.webui_crawler_source_routes import register_crawler_source_routes
from api.http.webui_crawler_sources_read_routes import register_crawler_sources_read_routes

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WEBUI_BACKEND = os.path.join(_ROOT, "CoreModules", "WebUIBackend")


def register_crawler_routes(bp: Blueprint, *, error_log: Any) -> None:
  """Register all crawler-related WebUI routes on ``bp``."""
  deps = {
      "error_log": error_log,
      "root": _ROOT,
      "webui_backend": _WEBUI_BACKEND,
      "get_crawler_sources_dir": get_crawler_sources_dir,
      "load_source_meta": load_source_meta,
      "load_sources_config": lambda: load_sources_config(_ROOT),
      "save_sources_config": lambda sources: save_sources_config(_ROOT, sources),
  }
  for register in (
      register_crawler_sources_read_routes,
      register_crawler_indexer_routes,
      register_crawler_md_pipeline_routes,
      register_crawler_job_routes,
  ):
      register(bp, **deps)
  register_crawler_source_routes(
      bp,
      error_log=error_log,
      get_crawler_sources_dir=get_crawler_sources_dir,
      load_source_meta=load_source_meta,
      load_sources_config=deps["load_sources_config"],
      save_sources_config=deps["save_sources_config"],
  )


__all__ = ["register_crawler_routes", "_clip_text_for_embedding", "_is_embed_context_length_error"]
