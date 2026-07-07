"""
Load pipeline from config/md_pipelines and run it on markdown.
Returns (page_meta, processed_body).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.md_indexer.application import steps as step_impl
from modules.md_indexer.domain.schema import Pipeline, Step


def _pipelines_dir() -> Path:
    """Directory containing pipeline JSON files (Core/config/md_pipelines)."""
    # Runner lives in Core/modules/md_indexer/application/; project root is 3 levels up from application
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    core_dir = project_root / "Core" / "config" / "md_pipelines"
    return core_dir if core_dir.is_dir() else project_root / "config" / "md_pipelines"


def get_active_pipeline_name() -> str:
    """Return active pipeline name from config or env (default: 'default')."""
    import os
    try:
        from config import get_indexing_dict
        cfg = get_indexing_dict("md_indexer", {})
        if isinstance(cfg, dict):
            name = cfg.get("active_pipeline")
            if name and isinstance(name, str) and name.strip():
                return name.strip()
    except Exception:  # safe: optional pipeline config; use env/default
        pass
    return os.environ.get("MD_INDEXER_PIPELINE", "default")


def list_pipeline_names() -> list[str]:
    """Return list of pipeline names (filenames without .json)."""
    d = _pipelines_dir()
    if not d.is_dir():
        return []
    names = []
    for f in d.iterdir():
        if f.suffix.lower() == ".json" and f.is_file():
            names.append(f.stem)
    return sorted(names)


def load_pipeline(name: str) -> Pipeline | None:
    """Load pipeline by name from config/md_pipelines/<name>.json."""
    d = _pipelines_dir()
    path = d / f"{name}.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return Pipeline.from_dict(data)


def save_pipeline(name: str, pipeline: Pipeline | dict[str, Any]) -> None:
    """Save pipeline to config/md_pipelines/<name>.json."""
    d = _pipelines_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.json"
    data = pipeline.to_dict() if isinstance(pipeline, Pipeline) else pipeline
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_pipeline(name: str) -> bool:
    """Delete pipeline config/md_pipelines/<name>.json. Returns True if removed."""
    d = _pipelines_dir()
    path = d / f"{name}.json"
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def run_pipeline(
    pipeline_name: str | dict[str, Any],
    md: str,
) -> tuple[dict[str, Any], str]:
    """
    Run the given pipeline on markdown.
    pipeline_name: either a string (load from config/md_pipelines/<name>.json) or a dict (pipeline definition).
    Returns (page_meta, processed_md).
    """
    if isinstance(pipeline_name, dict):
        pipeline = Pipeline.from_dict(pipeline_name)
    else:
        pipeline = load_pipeline(pipeline_name)
        if pipeline is None:
            return {}, md
    return _run_pipeline(pipeline, md)


def _run_pipeline(pipeline: Pipeline, md: str) -> tuple[dict[str, Any], str]:
    meta: dict[str, Any] = {}
    body = md or ""
    for step in pipeline.steps:
        if not isinstance(step, Step):
            step = Step(
                id=step.get("id", ""),
                type=step.get("type", ""),
                params=step.get("params") or {},
            )
        stype = step.type
        params = step.params or {}
        if stype == "strip_meta_block":
            meta, body = step_impl.step_strip_meta_block(body, params)
        elif stype == "delete_lines_exact":
            body = step_impl.step_delete_lines_exact(body, params)
        elif stype == "delete_lines_containing":
            body = step_impl.step_delete_lines_containing(body, params)
        elif stype == "delete_lines_regex":
            body = step_impl.step_delete_lines_regex(body, params)
        elif stype == "delete_sentences_starting_with":
            body = step_impl.step_delete_sentences_starting_with(body, params)
        elif stype == "delete_range_regex":
            body = step_impl.step_delete_range_regex(body, params)
        elif stype == "delete_regex_match":
            body = step_impl.step_delete_regex_match(body, params)
        elif stype == "strip_sections_by_heading":
            body = step_impl.step_strip_sections_by_heading(body, params)
        elif stype == "normalize_whitespace":
            body = step_impl.step_normalize_whitespace(body, params)
        elif stype == "wrap_indented_code":
            body = step_impl.step_wrap_indented_code(body, params)
        elif stype == "replace_regex":
            body = step_impl.step_replace_regex(body, params)
        elif stype == "reject_low_signal_body":
            body = step_impl.step_reject_low_signal_body(body, params)
    return (meta, body)
