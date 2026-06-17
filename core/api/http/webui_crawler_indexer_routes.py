"""Indexer tester routes for crawl sources."""

from __future__ import annotations

import difflib
import os
import random
import threading
import uuid
from typing import Any, Callable

from error_manager.http import error_response as _error_response
from flask import jsonify, request
from rag_service.application.params import get_rag_answer_params

from api.http.webui_provider_helpers import invoke_runtime_chat as _invoke_runtime_chat
from infrastructure.qdrant.collection_names import list_collection_names
from webui_backend.paths import webui_data_dir

try:
    from modules.md_indexer import get_active_pipeline_name, run_pipeline
except ImportError:
    get_active_pipeline_name = None  # type: ignore[assignment]
    run_pipeline = None  # type: ignore[assignment]

_ERROR_LOG: Any = None


def register_crawler_indexer_routes(
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

    @bp.route("/crawler/indexer-tester/sources", methods=["GET"])
    def get_indexer_tester_sources() -> Any:
        """
        List all crawl sources that have a pages/ directory with markdown files for Indexer Tester.
        """
        try:
            sources_dir = get_crawler_sources_dir()
            if not os.path.isdir(sources_dir):
                return jsonify({"sources": []})

            result: list[dict[str, Any]] = []
            for item in os.listdir(sources_dir):
                source_path = os.path.join(sources_dir, item)
                if not os.path.isdir(source_path):
                    continue
                pages_dir = os.path.join(source_path, "pages")
                if not os.path.isdir(pages_dir):
                    continue
                try:
                    files = [
                        name
                        for name in os.listdir(pages_dir)
                        if os.path.isfile(os.path.join(pages_dir, name))
                        and name.lower().endswith(".md")
                    ]
                except Exception:  # safe: unreadable page dir skipped in indexer tester listing
                    files = []
                result.append(
                    {
                        "id": item,
                        "page_count": len(files),
                    }
                )

            result.sort(key=lambda x: x["id"])
            return jsonify({"sources": result})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_sources", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/sources/<source_id>/files", methods=["GET"])
    def get_indexer_tester_files(source_id: str) -> Any:
        """
        List markdown files for a specific source, with optional sorting by name or size.
        """
        try:
            sources_dir = get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)

            sort_by = request.args.get("sort", "name")
            order = request.args.get("order", "asc")
            if sort_by not in ("name", "size"):
                sort_by = "name"
            if order not in ("asc", "desc"):
                order = "asc"

            files: list[dict[str, Any]] = []
            for name in os.listdir(pages_dir):
                if not name.lower().endswith(".md"):
                    continue
                full_path = os.path.join(pages_dir, name)
                if not os.path.isfile(full_path):
                    continue
                try:
                    size_bytes = os.path.getsize(full_path)
                except OSError:
                    size_bytes = 0
                files.append(
                    {
                        "filename": name,
                        "size_bytes": size_bytes,
                    }
                )

            reverse = order == "desc"
            if sort_by == "size":
                files.sort(key=lambda x: x["size_bytes"], reverse=reverse)
            else:
                files.sort(key=lambda x: x["filename"].lower(), reverse=reverse)

            return jsonify(
                {
                    "source_id": source_id,
                    "files": files,
                    "total": len(files),
                }
            )
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_files", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/sources/<source_id>/files/<path:filename>", methods=["GET"])
    def get_indexer_tester_file_detail(source_id: str, filename: str) -> Any:
        """
        Return original and processed markdown for a specific page using the WebUI backend pipeline.
        """
        try:
            sources_dir = get_crawler_sources_dir()
            pages_dir = os.path.join(sources_dir, source_id, "pages")
            if not os.path.isdir(pages_dir):
                return _error_response("Source pages directory not found", 404)

            # Normalize and validate path to stay under pages_dir
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                return _error_response("Invalid filename", 400)
            basename = os.path.basename(requested_path)
            if not basename.lower().endswith(".md"):
                return _error_response("Only .md files are supported", 400)
            if not os.path.isfile(requested_path):
                return _error_response("File not found", 404)

            meta = load_source_meta(source_id) or {}
            page_entry = (meta.get("pages") or {}).get(basename, {})

            with open(requested_path, "r", encoding="utf-8") as f:
                source_md = f.read()

            pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
            if run_pipeline is None:
                return _error_response("md_indexer module not available", 500)
            page_meta, processed_md = run_pipeline(pipeline_name, source_md)

            return jsonify(
                {
                    "source_id": source_id,
                    "filename": basename,
                    "page_meta": page_meta or page_entry or {},
                    "source_md": source_md,
                    "processed_md": processed_md,
                }
            )
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.get_indexer_tester_file_detail", exc_info=True)
            return _error_response(e)


    INDEXER_EVALUATE_SYSTEM_PROMPT_MAIN = """You are an expert on document processing for RAG. The user will provide PARSED METADATA (when available), then ORIGINAL markdown, PROCESSED markdown (after cleanup), and REMOVED CONTENT (the exact text that was deleted). Use REMOVED CONTENT to know precisely what was removed—do not guess from comparing ORIGINAL and PROCESSED.

    **Value rules (follow strictly):**
    - **Keep:** code examples, API signatures, configuration steps, migration notes, platform availability.
    - **Trim:** UI navigation text, empty headings, repeated descriptions, boilerplate sentences.
    - **Token efficiency:** Prefer keeping code examples and removing explanatory prose when both express the same concept. For developer RAG this works best.
    - If PROCESSED already contains a code example that demonstrates a concept, recommend removing explanatory paragraphs that only repeat what the code shows (common in Apple docs).
    - **Meta block:** Meta information is already preserved in metadata (see PARSED METADATA). The pipeline parses the meta comment into metadata and removes the comment from the text. Do not recommend restoring the meta comment block in the text. Do not suggest rules that target the comment syntax (e.g. delete_lines_exact with "<!--" or "-->"); that would break normal markdown.
    - **Code + explanation:** Keep at least one explanatory sentence for each code example. Do not recommend deleting all explanation and leaving only code; short explanations improve semantic retrieval.
    - **Inheritance / relationship sections:** Keep inheritance sections only if they contain concrete type names. Remove empty relationship sections (e.g. "Inherits From" with no content or only placeholder).
    - **Pipeline suggestions:** Do not suggest steps that contradict your analysis. Prefer structural rules (headings, UI text, boilerplate, section names). Avoid rules that target generic syntax tokens (e.g. "<!--", "-->", "```"); prefer rules tied to documentation structure. Avoid content-specific rules tied to a single document; such rules would break other documents.

    **Language:** Use the same language as the document. Do not translate quoted text.

    Answer in two sections with short bullet points. Be concrete: cite exact headings, phrases, or locations.

    **1. What in the PROCESSED text can still be trimmed:**
    - Apply the Trim rules above. List only concrete items: UI nav text, empty headings, repeated descriptions, boilerplate, or prose that duplicates code already in PROCESSED. One line per item; add a short quote or location if helpful.

    **2. What in REMOVED CONTENT was useful and should be kept:**
    - Look only at the REMOVED CONTENT block. List items that match the Keep rules (code, API signatures, config steps, migration notes, availability) and should be preserved by adjusting the pipeline. Do not list things that are still present in PROCESSED. Be specific so the pipeline can be adjusted."""

    INDEXER_EVALUATE_PIPELINE_STEPS_REF = """
    **Available pipeline step types** (you can suggest adding these to reduce noise or preserve useful content):

    - **strip_meta_block**: Remove leading <!-- meta ... --> HTML comment; parse meta (url, framework, etc.). No params.
    - **delete_lines_exact**: Remove lines that exactly match one of the given strings (e.g. "View in English", "Table of Contents"). Params: `lines` (list of strings), optional `case_sensitive` (bool).
    - **delete_lines_containing**: Remove lines that contain any of the given substrings (e.g. for "[View in English](url)" use substrings ["view in english"]). Params: `substrings` (list of strings), optional `case_sensitive` (bool).
    - **delete_lines_regex**: Remove each line that matches the regex. Params: `pattern` (string).
    - **delete_sentences_starting_with**: Remove whole prose sentences whose trimmed text starts with one of the prefixes, ignoring upper/lower case. Params: `prefixes` (list of strings).
    - **delete_range_regex**: Remove a range from first match of start_regex to first match of end_regex (or end of doc). Params: `start_regex`, optional `end_regex`.
    - **delete_regex_match**: Remove all non-overlapping matches of one regex (can be multiline). Params: `pattern` (string).
    - **strip_sections_by_heading**: Remove whole sections whose heading equals or starts with one of the list (e.g. "conforming types", "inherited by"). Params: `headings` (list of strings, lower case).
    - **normalize_whitespace**: Trim trailing space per line, collapse multiple spaces. No params.
    - **replace_regex**: Replace each match of pattern with replacement. Params: `pattern`, `replacement`.
    - **reject_low_signal_body**: After other steps, clear the body if it is too weak for RAG. Params: `min_chars` (e.g. 200), `min_words` (e.g. 5; use 0 to disable), `min_alpha_ratio` (0–1, e.g. 0.12; use 0 to disable). Place near the end of the pipeline.
    """

    INDEXER_EVALUATE_SYSTEM_PROMPT_SUGGEST = """
    **3. Suggested pipeline steps to add (required):**
    Always include section 3. Add a section "**3. Suggested pipeline steps to add:**". Based on sections 1 and 2, suggest one or more concrete pipeline steps that would improve this document's processing. For each suggestion give: step type (from the list above), and if the step has parameters, suggest concrete values (e.g. for delete_lines_exact suggest exact `lines: ["Advertisement", "Sign up"]`; for strip_sections_by_heading suggest `headings: ["see also"]`). If no steps would clearly help, write "None." Do not suggest steps that contradict your analysis. Do not suggest delete_lines_exact or delete_lines_containing with generic syntax like "<!--", "-->", or "```"—that would break markdown. Prefer structural rules (headings, UI text, boilerplate); avoid content-specific rules tied to a single document. Do not add a generic closing paragraph; end with the last suggested step or "None."
    """


    def _get_indexer_evaluate_system_prompt() -> str:
        return (
            INDEXER_EVALUATE_SYSTEM_PROMPT_MAIN
            + INDEXER_EVALUATE_PIPELINE_STEPS_REF
            + INDEXER_EVALUATE_SYSTEM_PROMPT_SUGGEST
        )


    # Sized for ~32k context: system + ORIGINAL + PROCESSED + REMOVED + response
    MAX_EVALUATE_CHARS = 40_000   # PROCESSED: ~10k tokens
    ORIGINAL_MAX_CHARS = 40_000   # ORIGINAL: ~10k tokens
    REMOVED_MAX_CHARS = 24_000    # REMOVED: ~6k tokens (~26k total for content, ~6k for system + reply)
    BATCH_EVAL_MIN_SIZE_BYTES = 1100  # 1.1 KB
    BATCH_EVAL_MIN_CHARS_AFTER_CLEANUP = 200  # after pipeline cleanup

    _batch_eval_jobs: dict[str, dict[str, Any]] = {}
    _batch_eval_lock = threading.Lock()


    def _compute_removed_content(original: str, processed: str, max_chars: int = 6_000) -> str:
        """Compute explicit diff: lines that were in original but removed (not in processed)."""
        if not original.strip():
            return "(empty original)"
        orig_lines = original.splitlines()
        proc_lines = processed.splitlines()
        matcher = difflib.SequenceMatcher(None, orig_lines, proc_lines)
        removed_lines = []
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag in ("delete", "replace"):
                removed_lines.extend(orig_lines[i1:i2])
        if not removed_lines:
            return "(nothing removed)"
        text = "\n".join(removed_lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[... truncated]"
        return text


    def _truncate_evaluate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n[... truncated]"


    PARSED_METADATA_KEY_ORDER = ("url", "framework", "availability", "doc_kind", "doc_scope", "doc_type")


    def _format_parsed_metadata(parsed_metadata: dict[str, Any]) -> str:
        """Format parsed metadata (e.g. from strip_meta_block) for the evaluation prompt. Key order: url, framework, availability, doc_kind, then rest."""
        if not parsed_metadata:
            return "(none)"
        lines = []
        seen = set()
        for k in PARSED_METADATA_KEY_ORDER:
            if k not in parsed_metadata:
                continue
            v = parsed_metadata[k]
            if v is None or v == "":
                continue
            if isinstance(v, (list, dict)):
                v = str(v)
            lines.append(f"{k}: {v}")
            seen.add(k)
        for k, v in sorted(parsed_metadata.items()):
            if k in seen:
                continue
            if v is None or v == "":
                continue
            if isinstance(v, (list, dict)):
                v = str(v)
            lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else "(none)"


    def _run_one_indexer_evaluate(
        source_md: str,
        processed_md: str,
        provider_id: str | None,
        model: str | None,
        chat_client: Any,
        params: Any,
        parsed_metadata: dict[str, Any] | None = None,
        original_max_chars: int | None = None,
        processed_max_chars: int | None = None,
        removed_max_chars: int | None = None,
    ) -> str:
        """Run a single LLM evaluation; returns reply text. Uses same prompts as indexer_tester_evaluate."""
        orig_max = original_max_chars if original_max_chars is not None else ORIGINAL_MAX_CHARS
        proc_max = processed_max_chars if processed_max_chars is not None else MAX_EVALUATE_CHARS
        rem_max = removed_max_chars if removed_max_chars is not None else REMOVED_MAX_CHARS
        source_md = _truncate_evaluate(source_md, orig_max)
        processed_md = _truncate_evaluate(processed_md, proc_max)
        removed_content = _compute_removed_content(
            source_md, processed_md, max_chars=rem_max
        )
        # Put PARSED METADATA first so the model sees that meta is already preserved before reading documents
        if parsed_metadata is not None:
            user_content = (
                "### PARSED METADATA\n\n"
                + _format_parsed_metadata(parsed_metadata)
                + "\n\n### ORIGINAL\n\n"
                + source_md
                + "\n\n### PROCESSED\n\n"
                + processed_md
                + "\n\n### REMOVED CONTENT\n\n"
                + removed_content
            )
        else:
            user_content = (
                "### ORIGINAL\n\n"
                + source_md
                + "\n\n### PROCESSED\n\n"
                + processed_md
                + "\n\n### REMOVED CONTENT\n\n"
                + removed_content
            )
        use_model = model if model else params.model_name
        if not use_model:
            raise ValueError("No chat model configured")
        system_prompt = _get_indexer_evaluate_system_prompt()
        provider_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options = {"temperature": 0.0}
        resolved_provider_id = str(provider_id or "").strip()
        if resolved_provider_id:
            return _invoke_runtime_chat(
                provider_id=resolved_provider_id,
                model=use_model,
                messages=provider_messages,
                options=options,
            )
        return chat_client.chat(provider_messages, use_model, stream=False, options=options) or ""


    def _batch_eval_worker(
        job_id: str,
        source_id: str,
        provider_id: str | None,
        model: str | None,
        count: int,
    ) -> None:
        sources_dir = get_crawler_sources_dir()
        pages_dir = os.path.join(sources_dir, source_id, "pages")
        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
            if not job or job["status"] != "running":
                return
        if not os.path.isdir(pages_dir):
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = "Source pages directory not found"
            return
        files: list[dict[str, Any]] = []
        for name in os.listdir(pages_dir):
            if not name.lower().endswith(".md"):
                continue
            full_path = os.path.join(pages_dir, name)
            if not os.path.isfile(full_path):
                continue
            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                size_bytes = 0
            if size_bytes < BATCH_EVAL_MIN_SIZE_BYTES:
                continue
            files.append({"filename": name, "size_bytes": size_bytes})
        # Keep only files that after pipeline cleanup have more than 200 characters
        if run_pipeline:
            pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
            filtered: list[dict[str, Any]] = []
            for entry in files:
                full_path = os.path.join(pages_dir, entry["filename"])
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        source_md = f.read()
                except Exception:  # safe: unreadable source file skipped in batch eval sampling
                    continue
                try:
                    _pm, processed_md = run_pipeline(pipeline_name, source_md)
                except Exception:  # safe: pipeline failure skips file in batch eval sampling
                    continue
                if len((processed_md or "").strip()) > BATCH_EVAL_MIN_CHARS_AFTER_CLEANUP:
                    filtered.append(entry)
            files = filtered
        random.shuffle(files)
        files = files[:count]
        total = len(files)
        with _batch_eval_lock:
            if job_id not in _batch_eval_jobs:
                return
            _batch_eval_jobs[job_id]["total"] = total
            _batch_eval_jobs[job_id]["results"] = []

        webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
        collection_name = (list_collection_names() or [None])[0]
        try:
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
        except Exception as e:
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = str(e)
            return
        chat_client = deps.chat_client
        use_model = model if model else (params.model_name if params else None)
        if not use_model:
            with _batch_eval_lock:
                if job_id in _batch_eval_jobs:
                    _batch_eval_jobs[job_id]["status"] = "error"
                    _batch_eval_jobs[job_id]["error"] = "No chat model configured"
            return

        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
        eval_orig_max = job.get("original_max_chars") if job else None
        eval_proc_max = job.get("processed_max_chars") if job else None
        eval_rem_max = job.get("removed_max_chars") if job else None

        for i, entry in enumerate(files):
            with _batch_eval_lock:
                if job_id not in _batch_eval_jobs or _batch_eval_jobs[job_id]["status"] != "running":
                    return
                _batch_eval_jobs[job_id]["current_file"] = entry["filename"]
            filename = entry["filename"]
            requested_path = os.path.abspath(os.path.join(pages_dir, filename))
            pages_dir_abs = os.path.abspath(pages_dir)
            if not requested_path.startswith(pages_dir_abs + os.sep):
                reply = "(invalid path)"
            else:
                try:
                    with open(requested_path, "r", encoding="utf-8") as f:
                        source_md = f.read()
                except Exception as e:
                    reply = f"(read error: {e})"
                else:
                    pipeline_name = get_active_pipeline_name() if get_active_pipeline_name else "default"
                    if run_pipeline:
                        try:
                            _pm, processed_md = run_pipeline(pipeline_name, source_md)
                        except Exception as e:
                            reply = f"(pipeline error: {e})"
                        else:
                            try:
                                reply = _run_one_indexer_evaluate(
                                    source_md,
                                    processed_md,
                                    provider_id,
                                    model,
                                    chat_client,
                                    params,
                                    parsed_metadata=_pm,
                                    original_max_chars=eval_orig_max,
                                    processed_max_chars=eval_proc_max,
                                    removed_max_chars=eval_rem_max,
                                )
                                if not (reply or "").strip():
                                    reply = "(empty response from model)"
                            except Exception as e:
                                reply = f"(LLM error: {e})"
                    else:
                        reply = "(pipeline not available)"
            with _batch_eval_lock:
                if job_id not in _batch_eval_jobs:
                    return
                _batch_eval_jobs[job_id]["done"] = i + 1
                _batch_eval_jobs[job_id]["results"].append({"filename": filename, "reply": reply})

        with _batch_eval_lock:
            if job_id in _batch_eval_jobs:
                _batch_eval_jobs[job_id]["status"] = "done"
                _batch_eval_jobs[job_id]["current_file"] = None


    @bp.route("/crawler/indexer-tester/evaluate", methods=["POST"])
    @bp.route("/crawler/indexer-tester/evaluate/", methods=["POST"])
    def indexer_tester_evaluate() -> Any:
        """
        Send original and processed markdown to the local LLM for pipeline evaluation.
        No RAG; single turn. Returns { "reply": content } or { "error": "..." }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_md = body.get("source_md") or ""
            processed_md = body.get("processed_md") or ""
            provider_id = (body.get("provider_id") or "").strip() or None
            model = (body.get("model") or "").strip() or None
            page_meta = body.get("page_meta") if isinstance(body.get("page_meta"), dict) else None
            try:
                orig_max = int(body.get("original_max_chars")) if body.get("original_max_chars") is not None else None
                proc_max = int(body.get("processed_max_chars")) if body.get("processed_max_chars") is not None else None
                rem_max = int(body.get("removed_max_chars")) if body.get("removed_max_chars") is not None else None
                if orig_max is not None and (orig_max < 1000 or orig_max > 500_000):
                    orig_max = None
                if proc_max is not None and (proc_max < 1000 or proc_max > 500_000):
                    proc_max = None
                if rem_max is not None and (rem_max < 1000 or rem_max > 500_000):
                    rem_max = None
            except (TypeError, ValueError):
                orig_max = proc_max = rem_max = None

            if not source_md and not processed_md:
                return _error_response("At least one of source_md or processed_md is required", 400)

            webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
            collection_name = None
            names = list_collection_names()
            if names:
                collection_name = names[0]
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
            chat_client = deps.chat_client
            content = _run_one_indexer_evaluate(
                source_md,
                processed_md,
                provider_id,
                model,
                chat_client,
                params,
                parsed_metadata=page_meta,
                original_max_chars=orig_max,
                processed_max_chars=proc_max,
                removed_max_chars=rem_max,
            )
            return jsonify({"reply": content or ""})
        except ValueError as e:
            return _error_response(e, 400)
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.indexer_tester_evaluate", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/evaluate-batch", methods=["POST"])
    def start_indexer_tester_evaluate_batch() -> Any:
        """Start a batch LLM evaluation job. Body: { source_id, model?, count }. Returns job_id."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_id = (body.get("source_id") or "").strip()
            provider_id = (body.get("provider_id") or "").strip() or None
            count = body.get("count")
            model = (body.get("model") or "").strip() or None
            if not source_id:
                return _error_response("source_id is required", 400)
            try:
                count = int(count) if count is not None else 0
            except (TypeError, ValueError):
                count = 0
            if count < 1 or count > 500:
                return _error_response("count must be between 1 and 500", 400)

            def _parse_limit(val: Any, default: int, min_val: int = 1000, max_val: int = 500_000) -> int:
                if val is None:
                    return default
                try:
                    n = int(val)
                    return max(min_val, min(max_val, n))
                except (TypeError, ValueError):
                    return default

            original_max = _parse_limit(body.get("original_max_chars"), ORIGINAL_MAX_CHARS)
            processed_max = _parse_limit(body.get("processed_max_chars"), MAX_EVALUATE_CHARS)
            removed_max = _parse_limit(body.get("removed_max_chars"), REMOVED_MAX_CHARS)

            job_id = str(uuid.uuid4())
            with _batch_eval_lock:
                _batch_eval_jobs[job_id] = {
                    "status": "running",
                    "total": 0,
                    "done": 0,
                    "current_file": None,
                    "results": [],
                    "error": None,
                    "source_id": source_id,
                    "original_max_chars": original_max,
                    "processed_max_chars": processed_max,
                    "removed_max_chars": removed_max,
                }
            thread = threading.Thread(
                target=_batch_eval_worker,
                args=(job_id, source_id, provider_id, model, count),
                daemon=True,
            )
            thread.start()
            return jsonify({"job_id": job_id})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.start_indexer_tester_evaluate_batch", exc_info=True)
            return _error_response(e)


    @bp.route("/crawler/indexer-tester/evaluate-batch/status/<job_id>", methods=["GET"])
    def get_indexer_tester_evaluate_batch_status(job_id: str) -> Any:
        """Return batch job state: status, total, done, current_file, results, error."""
        with _batch_eval_lock:
            job = _batch_eval_jobs.get(job_id)
        if not job:
            return _error_response("Job not found", 404)
        return jsonify({
            "job_id": job_id,
            "status": job["status"],
            "total": job["total"],
            "done": job["done"],
            "current_file": job.get("current_file"),
            "results": job.get("results") or [],
            "error": job.get("error"),
            "source_id": job.get("source_id"),
        })


    BATCH_PATTERNS_SYSTEM_PROMPT = """You are an expert on document processing for RAG. The user will provide a set of per-document evaluation replies from a batch run. Your task is to find **common patterns** across many documents and suggest **pipeline steps** that would improve processing for multiple documents at once.

    Rules:
    - Prefer structural rules (headings, UI text, boilerplate) that apply across docs.
    - Avoid content-specific rules tied to a single document (e.g. a phrase that appears in one file only).
    - Suggest concrete pipeline step types and parameters (e.g. strip_sections_by_heading with headings: ["see also", "relationships"]).
    - If you see the same recommendation in many replies (e.g. "empty ## Relationships section" in 40 docs), that is a strong candidate for one pipeline step.
    - Output: a short "Pattern" summary and "Suggested pipeline steps" with concrete steps. Be concise."""


    @bp.route("/crawler/indexer-tester/evaluate-batch/detect-patterns", methods=["POST"])
    def detect_batch_eval_patterns() -> Any:
        """
        Analyze batch evaluation results and return cross-document patterns and suggested pipeline steps.
        Body: { results: [{ filename, reply }, ...], model?: string }.
        Returns { patterns: "..." } or { error: "..." }.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            results = body.get("results") or []
            provider_id = (body.get("provider_id") or "").strip() or None
            model = (body.get("model") or "").strip() or None
            if not results or not isinstance(results, list):
                return _error_response("results array is required", 400)

            # Build content: one block per doc (filename + first N chars of reply) to stay within context
            max_reply_chars = 600
            max_docs = 80
            parts = []
            for i, item in enumerate(results[:max_docs]):
                if not isinstance(item, dict):
                    continue
                fn = item.get("filename") or f"doc_{i}"
                reply = (item.get("reply") or "").strip()
                if len(reply) > max_reply_chars:
                    reply = reply[:max_reply_chars] + "\n[...]"
                parts.append(f"--- {fn} ---\n{reply}")
            if not parts:
                return _error_response("No valid results to analyze", 400)
            user_content = (
                "Below are per-document evaluation replies from a batch of "
                + str(len(results))
                + " files. Identify common patterns and suggest pipeline steps that would help many documents.\n\n"
                + "\n\n".join(parts)
            )

            webui_dir = str(webui_data_dir()) if webui_data_dir().is_dir() else None
            collection_name = (list_collection_names() or [None])[0]
            params, deps = get_rag_answer_params(webui_dir=webui_dir, collection_name=collection_name)
            chat_client = deps.chat_client
            use_model = model or (params.model_name if params else None)
            if not use_model:
                return _error_response("No chat model configured", 400)

            system_prompt = BATCH_PATTERNS_SYSTEM_PROMPT
            provider_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            options = {"temperature": 0.0}
            if provider_id:
                patterns = _invoke_runtime_chat(
                    provider_id=provider_id,
                    model=use_model,
                    messages=provider_messages,
                    options=options,
                )
            else:
                patterns = chat_client.chat(provider_messages, use_model, stream=False, options=options) or ""
            return jsonify({"patterns": (patterns or "").strip()})
        except Exception as e:
            _ERROR_LOG.error("webui_crawler_routes.detect_batch_eval_patterns", exc_info=True)
            return _error_response(e)





__all__ = ["register_crawler_indexer_routes"]
