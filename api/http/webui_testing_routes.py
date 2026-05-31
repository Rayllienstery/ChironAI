"""Testing-only WebUI routes (external docs preview, etc.)."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from error_manager.http import error_response as _error_response


def register_testing_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    external_docs_rag_available: bool,
    run_pipeline: Callable[[str, str], tuple[Any, Any]] | None,
    get_active_pipeline_name: Callable[[], str | None] | None,
) -> None:
    @bp.route("/testing/external-docs/preview", methods=["POST"])
    def testing_external_docs_preview() -> Any:
        if run_pipeline is None:
            return _error_response("md_indexer module not available", 500)
        if not external_docs_rag_available:
            return _error_response("external_docs_rag module not available", 500)
        try:
            body = request.get_json(force=True, silent=True) or {}
            library = (body.get("library") or body.get("name") or "").strip()
            if not library:
                return _error_response("library is required", 400)

            max_files_raw = body.get("max_files")
            max_chars_raw = body.get("max_chars_per_file")
            pipeline_name = body.get("pipeline_name")

            try:
                max_files = int(max_files_raw) if max_files_raw is not None else 10
            except Exception:
                max_files = 10
            max_files = max(1, min(50, max_files))

            try:
                max_chars_per_file = int(max_chars_raw) if max_chars_raw is not None else 80000
            except Exception:
                max_chars_per_file = 80000
            max_chars_per_file = max(2000, min(300000, max_chars_per_file))

            if pipeline_name is None and get_active_pipeline_name is not None:
                pipeline_name = get_active_pipeline_name()

            from external_docs_rag.infrastructure import HttpFetchClient
            from external_docs_rag.infrastructure.github_discovery import (
                GITHUB_RAW_TEMPLATE,
                discover_repo,
            )
            from external_docs_rag.infrastructure.github_tree import list_markdown_paths
            from external_docs_rag.infrastructure.parsing import parse_document_to_markdown

            resolved = discover_repo(library)
            if not resolved:
                return jsonify({
                    "ok": True,
                    "library": library,
                    "resolved": {
                        "found": False,
                        "label": library,
                        "repo_full_name": None,
                        "primary_url": None,
                    },
                    "pipeline": {"name": pipeline_name or "", "applied": True},
                    "documents": [],
                })

            full_name, default_branch = resolved
            owner, repo = full_name.split("/", 1)
            ref = default_branch or "main"

            paths = list_markdown_paths(owner, repo, ref, max_depth=3)
            paths_sorted: list[str] = []
            for p in paths:
                if p.lower() == "readme.md":
                    paths_sorted.insert(0, p)
                else:
                    paths_sorted.append(p)
            paths_sorted = paths_sorted[:max_files]

            primary_url = GITHUB_RAW_TEMPLATE.format(full_name=full_name, ref=ref)

            if not paths_sorted:
                return jsonify({
                    "ok": True,
                    "library": library,
                    "resolved": {
                        "found": True,
                        "label": library,
                        "repo_full_name": full_name,
                        "primary_url": primary_url,
                    },
                    "pipeline": {"name": pipeline_name or "", "applied": True},
                    "documents": [],
                })

            fetch_client = HttpFetchClient()
            documents: list[dict[str, Any]] = []
            for path in paths_sorted:
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
                raw_md = ""
                processed_md = ""
                err: str | None = None
                try:
                    doc = fetch_client.fetch(url)
                    if doc is None:
                        raise RuntimeError("Fetch failed")
                    md = parse_document_to_markdown(doc) or ""
                    raw_md = md[:max_chars_per_file]
                    _, processed_md = run_pipeline(pipeline_name or "", raw_md)
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                documents.append({
                    "filename": path,
                    "url": url,
                    "raw_md": raw_md,
                    "processed_md": processed_md,
                    "error": err,
                })

            primary_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{paths_sorted[0]}"
            return jsonify({
                "ok": True,
                "library": library,
                "resolved": {
                    "found": True,
                    "label": library,
                    "repo_full_name": full_name,
                    "primary_url": primary_url,
                },
                "pipeline": {"name": pipeline_name or "", "applied": True},
                "documents": documents,
            })
        except Exception as e:
            error_log.error("webui_testing_routes.testing_external_docs_preview", exc_info=True)
            return _error_response(e)
