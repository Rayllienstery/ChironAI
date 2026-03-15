"""
MD Indexer: config-driven markdown cleanup pipeline for RAG indexing.

Pipeline is defined in JSON (e.g. config/md_pipelines/*.json). No hardcoded rules in Python.
"""

from __future__ import annotations

from modules.md_indexer.application.runner import (
    delete_pipeline,
    get_active_pipeline_name,
    list_pipeline_names,
    load_pipeline,
    run_pipeline,
    save_pipeline,
)

__all__ = [
    "delete_pipeline",
    "get_active_pipeline_name",
    "list_pipeline_names",
    "load_pipeline",
    "run_pipeline",
    "save_pipeline",
]
