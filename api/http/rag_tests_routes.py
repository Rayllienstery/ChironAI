"""
Dedicated Flask routes for RAG tests management and execution.

Split from api.http.webui_routes to keep WebUI composition slim and make
RAG tests orchestration independently maintainable.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, Response, current_app, jsonify, request

from application.rag.proxy_settings_contract import load_proxy_settings, resolve_rag_collection
from application.rag_tests.runner import build_proxy_chat_payload
from config import get_qdrant_url
from core.contracts.webui_api import WEBUI_URL_PREFIX
from api.http.proxy_trace import get_current_trace, recent_proxy_traces
from infrastructure.database import get_rag_test_runs_repository, get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger

rag_tests_bp = Blueprint("rag_tests", __name__, url_prefix=WEBUI_URL_PREFIX)
_ERROR_LOG = get_webui_error_logger()


def _get_qdrant_collection_names() -> list[str]:
    """Return list of Qdrant collection names (empty if unavailable)."""
    url = get_qdrant_url().rstrip("/")
    try:
        resp = requests.get(f"{url}/collections", timeout=5.0)
        if not resp.ok:
            return []
        data = resp.json() or {}
        raw = data.get("result", {}).get("collections", []) if isinstance(data, dict) else []
        names: list[str] = []
        for col in raw:
            if isinstance(col, dict):
                name = col.get("name")
            else:
                name = str(col)
            if name:
                names.append(name)
        return names
    except Exception:
        return []

# ----- RAG Tests (Markdown-defined tests, run against proxy, validate concepts + RAG) -----
# In-memory job store for async run with progress and cancel
_rag_test_jobs: dict[str, dict[str, Any]] = {}
_rag_test_jobs_lock = threading.Lock()


def _get_rag_tests_module():
    try:
        from application.rag_tests.loader import (
            get_rag_tests_root,
            list_test_filters,
            load_all_tests,
            load_test,
        )
        from application.rag_tests.validator import validate_result
        return get_rag_tests_root, list_test_filters, load_all_tests, load_test, validate_result
    except ImportError:
        return None, None, None, None, None


def _find_trace_by_client_request_id(request_id: str) -> dict[str, Any] | None:
    """Find most recent trace for a request id from in-memory ring buffer/current snapshot."""
    rid = str(request_id or "").strip()
    if not rid:
        return None
    try:
        for tr in reversed(recent_proxy_traces(limit=80)):
            if not isinstance(tr, dict):
                continue
            req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
            if str(req.get("client_request_id") or "") == rid:
                return tr
    except Exception:
        pass
    tr = get_current_trace() or {}
    if isinstance(tr, dict):
        req = tr.get("request") if isinstance(tr.get("request"), dict) else {}
        if str(req.get("client_request_id") or "") == rid:
            return tr
    return None


def _live_rag_step_timings(trace: dict[str, Any] | None, elapsed_ms: int) -> dict[str, float]:
    """Build live step timings for current test from trace + elapsed wall time."""
    out: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "rerank_s": 0.0,
        "total_rag_s": 0.0,
        "chat_s_estimated": max(0.0, float(elapsed_ms) / 1000.0),
        "latency_s_total": max(0.0, float(elapsed_ms) / 1000.0),
    }
    if not isinstance(trace, dict):
        return out
    rag = trace.get("rag") if isinstance(trace.get("rag"), dict) else {}
    timings = rag.get("timings") if isinstance(rag.get("timings"), dict) else {}
    if not isinstance(timings, dict):
        return out
    for k in ("embed_s", "search_s", "rerank_s", "total_rag_s"):
        try:
            if timings.get(k) is not None:
                out[k] = max(0.0, float(timings.get(k) or 0.0))
        except Exception:
            pass
    total_s = max(0.0, float(elapsed_ms) / 1000.0)
    try:
        resp = trace.get("response") if isinstance(trace.get("response"), dict) else {}
        if resp.get("latency_ms") is not None:
            total_s = max(0.0, float(resp.get("latency_ms") or 0.0) / 1000.0)
    except Exception:
        pass
    out["latency_s_total"] = total_s
    out["chat_s_estimated"] = max(0.0, total_s - float(out.get("total_rag_s") or 0.0))
    return out


def _run_unified_proxy_chat(body: dict[str, Any]) -> Any:
    """Delegate chat handling to /v1 chat_completions core to avoid duplicate RAG logic."""
    wiring = current_app.extensions.get("llm_proxy_wiring")
    if wiring is None:
        return jsonify({"error": "LLM proxy wiring not initialized"}), 500
    from llm_proxy.chat_completions import run_chat_completions

    return run_chat_completions(wiring, body_override=body)


@rag_tests_bp.route("/rag-tests", methods=["GET"])
def rag_tests_list() -> Any:
    """List all RAG tests, optionally filtered by platform, framework, difficulty."""
    get_root, list_filters, load_all, load_one, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = get_root()
    tests = load_all(root)
    platform = (request.args.get("platform") or "").strip()
    framework = (request.args.get("framework") or "").strip()
    difficulty = (request.args.get("difficulty") or "").strip()
    if platform:
        tests = [t for t in tests if (t.get("platform") or "") == platform]
    if framework:
        tests = [t for t in tests if (t.get("framework") or "") == framework]
    if difficulty:
        tests = [t for t in tests if (t.get("difficulty") or "") == difficulty]
    filters = list_filters(tests) if list_filters else {"platform": [], "framework": [], "difficulty": []}
    return jsonify({"tests": tests, "filters": filters})


@rag_tests_bp.route("/rag-tests/filters", methods=["GET"])
def rag_tests_filters() -> Any:
    """Return distinct platform, framework, difficulty for filter dropdowns."""
    _, list_filters, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = _get_rag_tests_module()[0]()
    tests = load_all(root)
    filters = list_filters(tests) if list_filters else {"platform": [], "framework": [], "difficulty": []}
    return jsonify(filters)


@rag_tests_bp.route("/rag-tests/runs", methods=["GET"])
def rag_tests_runs_list() -> Any:
    """List past RAG test runs (history). Query: limit, offset, model, from_date, to_date, status."""
    try:
        repo = get_rag_test_runs_repository()
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = max(0, int(request.args.get("offset", 0)))
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        status = (request.args.get("status") or "").strip() or None
        runs = repo.get_runs(
            limit=limit,
            offset=offset,
            model=model,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )
        return jsonify({"runs": runs})
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_runs_list")
        return jsonify({"error": str(e)}), 500


@rag_tests_bp.route("/rag-tests/runs/summary", methods=["GET"])
def rag_tests_runs_summary() -> Any:
    """Aggregate metrics for runs. Query: limit (default 50), model, from_date, to_date."""
    try:
        repo = get_rag_test_runs_repository()
        limit = min(int(request.args.get("limit", 50)), 200)
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        summary = repo.get_runs_summary(
            limit=limit,
            model=model,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify(summary)
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_runs_summary")
        return jsonify({"error": str(e)}), 500


@rag_tests_bp.route("/rag-tests/runs/<run_id>", methods=["GET"])
def rag_tests_run_detail(run_id: str) -> Any:
    """Get a single past run with full results. Query param format=csv returns CSV attachment."""
    export_format = (request.args.get("format") or "").strip().lower()
    if export_format == "csv":
        return _rag_tests_export_run(run_id, "csv")
    try:
        repo = get_rag_test_runs_repository()
        run = repo.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(run)
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_run_detail")
        return jsonify({"error": str(e)}), 500


@rag_tests_bp.route("/rag-tests/runs/<run_id>/export", methods=["GET"])
def rag_tests_run_export(run_id: str) -> Any:
    """Export run as JSON or CSV attachment. Query param format=csv|json (default json)."""
    export_format = (request.args.get("format") or "json").strip().lower()
    if export_format not in ("json", "csv"):
        export_format = "json"
    return _rag_tests_export_run(run_id, export_format)


def _rag_tests_export_run(run_id: str, export_format: str) -> Any:
    """Return run data as JSON or CSV with Content-Disposition."""
    try:
        repo = get_rag_test_runs_repository()
        run = repo.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_export_run")
        return jsonify({"error": str(e)}), 500
    created = run.get("created_at") or ""
    safe_date = created.replace(":", "-").replace(" ", "_")[:19] if created else "run"
    filename = f"rag-test-run-{run_id}-{safe_date}.{export_format}"
    if export_format == "csv":
        import csv
        import io
        rows = [["test_id", "test_name", "platform", "framework", "status", "response_time_ms", "rag_used", "confidence_label", "question", "error"]]
        for r in (run.get("results") or []):
            rows.append([
                r.get("test_id") or "",
                r.get("test_name") or "",
                r.get("platform") or "",
                r.get("framework") or "",
                r.get("status") or "",
                str(r.get("response_time_ms") or ""),
                "yes" if r.get("rag_used") else "no",
                r.get("confidence_label") or "",
                (r.get("question") or "").replace("\r", " ").replace("\n", " "),
                r.get("error") or "",
            ])
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerows(rows)
        body = buf.getvalue()
        resp = Response(body, mimetype="text/csv")
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    # JSON
    body = json.dumps(run, indent=2)
    resp = Response(body, mimetype="application/json")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _rag_tests_find_by_id(get_root: Any, load_all: Any, test_id: str) -> dict[str, Any] | None:
    """Return test dict with absolute_path if found, else None."""
    if load_all is None:
        return None
    root = Path(get_root())
    tests = load_all(root)
    for t in tests:
        if t.get("id") == test_id:
            return t
    return None


def _normalize_concepts(raw_concepts: list[str]) -> list[str]:
    """
    Normalize Expected Concepts coming from the WebUI/CLI.

    Rules:
    - One atomic concept per entry (no combined lists like `weak / unowned`).
    - Trim whitespace and drop empty entries.
    - Split on common separators (`/`, `,`, `;`, ` and `) when they clearly
      represent multiple concepts, for example:
        - \"weak / unowned\" -> [\"weak\", \"unowned\"]
        - \"weak and unowned\" -> [\"weak\", \"unowned\"]
    - If the string still looks ambiguous after splitting (mixture of
      separators, very long phrase), keep it as-is so the author can fix it.
    """
    normalized: list[str] = []
    for item in raw_concepts:
        text = (item or "").strip()
        if not text:
            continue

        lowered = text.lower()
        # Fast path: no obvious separators, treat as a single concept.
        if all(sep not in lowered for sep in ("/", ",", ";", " and ")):
            normalized.append(text)
            continue

        # Handle the most common simple patterns safely.
        # Priority: explicit " and " between two short tokens, or slash/comma-separated tokens.
        candidates: list[str] = []

        def _split_and_extend(separator: str) -> None:
            parts = [p.strip() for p in text.split(separator) if p.strip()]
            if len(parts) >= 2:
                candidates.extend(parts)

        # Try word-level conjunction first.
        if " and " in lowered:
            _split_and_extend(" and ")
        # Then symbol-based separators.
        if "/" in text:
            _split_and_extend("/")
        if "," in text:
            _split_and_extend(",")
        if ";" in text:
            _split_and_extend(";")

        # Heuristic: if we obtained at least two reasonably short pieces and
        # the combined length is similar to the original, treat them as
        # separate atomic concepts. Otherwise, keep the original string so
        # that the test author can adjust it explicitly.
        if len(candidates) >= 2 and all(len(c) <= 40 for c in candidates):
            for c in candidates:
                if c and c not in normalized:
                    normalized.append(c)
            continue

        normalized.append(text)

    return normalized


def _rag_tests_build_md(
    name: str,
    question: str,
    concepts: list[str],
    platform: str,
    framework: str,
    difficulty: str,
    concept_mode: str,
    rag_strict: bool,
    min_os: str,
    notes: str,
) -> str:
    """Build .md file content for create/update."""
    lines = [
        f"# {name}",
        "",
        f"Platform: {platform}",
        f"Framework: {framework}",
        f"Difficulty: {difficulty}",
        f"Concept Mode: {concept_mode}",
    ]
    if rag_strict:
        lines.append("RAG Strict: true")
    if min_os:
        lines.append(f"MinOS: {min_os}")
    lines.extend(["", "## Question", "", question, "", "## Expected Concepts", ""])
    for c in concepts:
        lines.append(f"- {c}")
    lines.extend(["", "## RAG Requirement", "", "The answer must reference retrieved documentation or RAG context.", ""])
    if notes:
        lines.extend(["## Notes", "", notes])
    return "\n".join(lines)


@rag_tests_bp.route("/rag-tests/<test_id>", methods=["GET"])
def rag_tests_get_one(test_id: str) -> Any:
    """Get a single RAG test by id (path-based id)."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    root = get_root()
    tests = load_all(root)
    for t in tests:
        if t.get("id") == test_id:
            return jsonify(t)
    return jsonify({"error": "Test not found"}), 404


@rag_tests_bp.route("/rag-tests/<test_id>", methods=["PUT"])
def rag_tests_update(test_id: str) -> Any:
    """Update an existing RAG test. Body same as create. Overwrites the .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    t = _rag_tests_find_by_id(get_root, load_all, test_id)
    if not t:
        return jsonify({"error": "Test not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or body.get("question") or "Untitled test")[:200].strip()
    question = (body.get("question") or "").strip()
    concepts = body.get("concepts") or body.get("expected_concepts") or []
    if isinstance(concepts, str):
        concepts = [c.strip() for c in concepts.split("\n") if c.strip()]
    concepts = _normalize_concepts(list(concepts))
    platform = (body.get("platform") or "iOS").strip()
    framework = (body.get("framework") or "SwiftUI").strip()
    difficulty = (body.get("difficulty") or "intermediate").strip()
    concept_mode = (body.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    rag_strict = bool(body.get("rag_strict"))
    min_os = (body.get("min_os") or "").strip()
    notes = (body.get("notes") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    # Slug from name or first line of question
    slug = re.sub(r"[^\w\s-]", "", name).strip()
    slug = re.sub(r"[-\s]+", "_", slug).lower()[:80] or "test"
    root = Path(get_root())
    platform_dir = root / platform.lower().replace(" ", "_")
    framework_dir = platform_dir / framework.lower().replace(" ", "_")
    framework_dir.mkdir(parents=True, exist_ok=True)
    path = framework_dir / f"{slug}.md"
    if path.exists():
        n = 1
        while (framework_dir / f"{slug}_{n}.md").exists():
            n += 1
        path = framework_dir / f"{slug}_{n}.md"
        slug = f"{slug}_{n}"
    content = _rag_tests_build_md(
        name, question, concepts, platform, framework, difficulty, concept_mode, rag_strict, min_os, notes
    )
    path.write_text(content, encoding="utf-8")
    test_id = str(path.relative_to(root)).replace(".md", "").replace("/", "_").replace("\\", "_")
    return jsonify({"id": test_id, "file_path": str(path.relative_to(root)), "message": "Test created"}), 201


@rag_tests_bp.route("/rag-tests/<test_id>", methods=["DELETE"])
def rag_tests_delete(test_id: str) -> Any:
    """Delete a RAG test by removing its .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    t = _rag_tests_find_by_id(get_root, load_all, test_id)
    if not t:
        return jsonify({"error": "Test not found"}), 404
    path = Path(t["absolute_path"])
    if path.exists():
        path.unlink()
    return "", 204


def _rag_tests_run_worker(
    job_id: str,
    app_context: Any,
    tests_to_run: list[dict[str, Any]],
    model: str,
    collection_name: str,
    prompt_name: str | None = None,
    temperature: float | None = None,
    top_k: float | None = None,
    concurrency: int = 1,
    testing_disable_rerank: bool = False,
) -> None:
    """Background worker: run tests concurrently, update progress, respect cancel."""
    with app_context:
        app = current_app._get_current_object()
        get_root, _, _, _, validate_result = _get_rag_tests_module()
        if validate_result is None:
            with _rag_test_jobs_lock:
                _rag_test_jobs[job_id]["status"] = "completed"
                _rag_test_jobs[job_id]["error"] = "RAG tests module not available"
            return

        max_workers = max(1, min(int(concurrency or 1), 8))
        total = len(tests_to_run)
        results: list[dict[str, Any]] = []
        passed = 0
        failed = 0
        completed = 0
        launched = 0
        active_tests: dict[int, str] = {}
        active_live: dict[int, dict[str, Any]] = {}
        active_tests_lock = threading.Lock()

        def _default_live_timings() -> dict[str, float]:
            return {
                "embed_s": 0.0,
                "search_s": 0.0,
                "rerank_s": 0.0,
                "total_rag_s": 0.0,
                "chat_s_estimated": 0.0,
                "latency_s_total": 0.0,
            }

        def _set_progress(*, force_clear_sse: bool = False) -> None:
            with active_tests_lock:
                active_snapshot = dict(active_tests)
                live_snapshot = {k: dict(v) for k, v in active_live.items()}
            with _rag_test_jobs_lock:
                job = _rag_test_jobs.get(job_id)
                if not job:
                    return
                pr = dict(job.get("progress") or {})
                active_count = len(active_snapshot)
                active_items: list[dict[str, Any]] = []
                for idx, name in sorted(active_snapshot.items(), key=lambda x: x[0]):
                    src = live_snapshot.get(idx) or {}
                    active_items.append({
                        "index": int(idx + 1),
                        "name": str(name),
                        "started_at_ms": src.get("started_at_ms"),
                        "sse_enabled": bool(src.get("sse_enabled")),
                        "sse_preview": str(src.get("sse_preview") or ""),
                        "sse_tokens_generated_est": int(src.get("sse_tokens_generated_est") or 0),
                        "sse_token_tps_live": src.get("sse_token_tps_live"),
                        "sse_token_tps_avg": src.get("sse_token_tps_avg"),
                        "current_step_timings": (
                            src.get("current_step_timings")
                            if isinstance(src.get("current_step_timings"), dict)
                            else _default_live_timings()
                        ),
                    })
                primary = active_items[0] if active_items else None
                if force_clear_sse and not primary:
                    pr["sse_enabled"] = False
                    pr["sse_preview"] = ""
                    pr["sse_tokens_generated_est"] = 0
                    pr["sse_token_tps_live"] = None
                    pr["sse_token_tps_avg"] = None
                    pr["current_step_timings"] = _default_live_timings()
                elif primary:
                    pr["sse_enabled"] = bool(primary.get("sse_enabled"))
                    pr["sse_preview"] = str(primary.get("sse_preview") or "")
                    pr["sse_tokens_generated_est"] = int(primary.get("sse_tokens_generated_est") or 0)
                    pr["sse_token_tps_live"] = primary.get("sse_token_tps_live")
                    pr["sse_token_tps_avg"] = primary.get("sse_token_tps_avg")
                    pr["current_step_timings"] = (
                        primary.get("current_step_timings")
                        if isinstance(primary.get("current_step_timings"), dict)
                        else _default_live_timings()
                    )
                pr["current_index"] = completed + active_count
                pr["total"] = total
                pr["current_test_name"] = next(iter(active_snapshot.values()), "")
                pr["active_tests"] = list(active_snapshot.values())
                pr["active_live"] = active_items
                pr["active_count"] = active_count
                pr["max_concurrency"] = max_workers
                pr["passed"] = passed
                pr["failed"] = failed
                pr["pending"] = max(0, total - completed - active_count)
                job["progress"] = pr
                job["results"] = sorted(results, key=lambda r: int(r.get("_order", 0)))

        def _execute_single(idx: int, test: dict[str, Any]) -> dict[str, Any]:
            question = test.get("question") or ""
            start_time = time.time()
            with app.app_context():
                client = app.test_client()
                try:
                    request_id = f"ragtest-{job_id}-{idx+1}"
                    chat_payload = build_proxy_chat_payload(
                        question=question,
                        model=model,
                        collection_name=collection_name,
                        client_request_id=request_id,
                        prompt_name=prompt_name,
                        temperature=temperature,
                        top_k=top_k,
                        testing_disable_rerank=testing_disable_rerank,
                    )
                    resp = client.post("/v1/chat/completions", json=chat_payload, buffered=False)
                    content_type = str(resp.headers.get("Content-Type") or "")
                    is_sse_response = "text/event-stream" in content_type.lower()
                    with active_tests_lock:
                        if idx in active_tests:
                            current = dict(active_live.get(idx) or {})
                            current["sse_enabled"] = bool(is_sse_response)
                            current["current_step_timings"] = _live_rag_step_timings(
                                _find_trace_by_client_request_id(request_id),
                                int((time.time() - start_time) * 1000),
                            )
                            active_live[idx] = current
                    _set_progress()
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    if resp.status_code != 200:
                        data = resp.get_json(silent=True) or {}
                        err = data.get("error", resp.get_data(as_text=True))
                        return {
                            "_order": idx,
                            "test_id": test.get("id"),
                            "test_name": test.get("name"),
                            "platform": test.get("platform"),
                            "framework": test.get("framework"),
                            "difficulty": test.get("difficulty"),
                            "model": model,
                            "status": "FAIL",
                            "response_time_ms": elapsed_ms,
                            "latency_ms": elapsed_ms,
                            "rag_used": False,
                            "confidence_label": "0/0",
                            "missing_concepts": test.get("expected_concepts") or [],
                            "found_concepts": [],
                            "full_response": None,
                            "chunks_info": [],
                            "rag_queries": [],
                            "retrieved_chunks": None,
                            "question": question,
                            "prompt_tokens": None,
                            "completion_tokens": None,
                            "total_tokens": None,
                            "context_chars": None,
                            "failure_reason": str(err),
                            "error": str(err),
                        }

                    sse_buf = ""
                    sse_full = ""
                    last_rate_ts = time.time()
                    last_rate_tokens = 0
                    for piece in resp.response:
                        text = piece.decode("utf-8", errors="replace") if isinstance(piece, (bytes, bytearray)) else str(piece)
                        sse_buf += text
                        while "\n" in sse_buf:
                            line, sse_buf = sse_buf.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if not payload or payload == "[DONE]":
                                continue
                            try:
                                obj = json.loads(payload)
                            except Exception:
                                continue
                            choices = obj.get("choices") if isinstance(obj, dict) else None
                            if not isinstance(choices, list) or not choices:
                                continue
                            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                            if not isinstance(delta, dict):
                                continue
                            part = delta.get("content")
                            if isinstance(part, str) and part:
                                sse_full += part
                                now_ts = time.time()
                                elapsed_total_s = max(0.001, now_ts - start_time)
                                generated_tokens_est = max(0, int(len(sse_full) / 4))
                                delta_t = max(0.001, now_ts - last_rate_ts)
                                delta_tokens = max(0, generated_tokens_est - last_rate_tokens)
                                live_tps = float(delta_tokens) / delta_t
                                avg_tps = float(generated_tokens_est) / elapsed_total_s
                                last_rate_ts = now_ts
                                last_rate_tokens = generated_tokens_est
                                with active_tests_lock:
                                    if idx in active_tests:
                                        current = dict(active_live.get(idx) or {})
                                        current["sse_enabled"] = bool(is_sse_response)
                                        current["sse_preview"] = sse_full[-1600:]
                                        current["sse_tokens_generated_est"] = generated_tokens_est
                                        current["sse_token_tps_live"] = live_tps
                                        current["sse_token_tps_avg"] = avg_tps
                                        current["current_step_timings"] = _live_rag_step_timings(
                                            _find_trace_by_client_request_id(request_id),
                                            int((time.time() - start_time) * 1000),
                                        )
                                        active_live[idx] = current
                                _set_progress()

                    elapsed_total_ms = int((time.time() - start_time) * 1000)
                    content = sse_full
                    trace = _find_trace_by_client_request_id(request_id) or {}
                    trace_ok = bool(trace)
                    trace_rag = trace.get("rag") if trace_ok and isinstance(trace.get("rag"), dict) else {}
                    trace_ctx = trace_rag.get("context") if isinstance(trace_rag.get("context"), dict) else {}
                    trace_chunks = trace_ctx.get("chunks") if isinstance(trace_ctx.get("chunks"), list) else []
                    trace_timings = trace_rag.get("timings") if isinstance(trace_rag.get("timings"), dict) else {}
                    trace_ollama = trace.get("ollama") if trace_ok and isinstance(trace.get("ollama"), dict) else {}
                    trace_tokens = trace_ollama.get("tokens_estimates") if isinstance(trace_ollama.get("tokens_estimates"), dict) else {}
                    trace_resp = trace.get("response") if trace_ok and isinstance(trace.get("response"), dict) else {}
                    latency_ms = int(trace_resp.get("latency_ms") or elapsed_total_ms)
                    output_tokens_exact = None
                    prompt_tokens_exact = None
                    try:
                        if trace_resp.get("ollama_eval_count") is not None:
                            output_tokens_exact = int(trace_resp.get("ollama_eval_count"))
                    except Exception:
                        output_tokens_exact = None
                    try:
                        if trace_resp.get("ollama_prompt_eval_count") is not None:
                            prompt_tokens_exact = int(trace_resp.get("ollama_prompt_eval_count"))
                    except Exception:
                        prompt_tokens_exact = None
                    if isinstance(trace_timings, dict):
                        trace_timings = dict(trace_timings)
                        try:
                            total_rag_s = float(trace_timings.get("total_rag_s") or 0.0)
                        except Exception:
                            total_rag_s = 0.0
                        trace_timings["chat_s_estimated"] = max(0.0, (latency_ms / 1000.0) - total_rag_s)
                        trace_timings["latency_s_total"] = max(0.0, latency_ms / 1000.0)
                        with active_tests_lock:
                            if idx in active_tests:
                                current = dict(active_live.get(idx) or {})
                                current["current_step_timings"] = {
                                    "embed_s": float(trace_timings.get("embed_s") or 0.0),
                                    "search_s": float(trace_timings.get("search_s") or 0.0),
                                    "rerank_s": float(trace_timings.get("rerank_s") or 0.0),
                                    "total_rag_s": float(trace_timings.get("total_rag_s") or 0.0),
                                    "chat_s_estimated": float(trace_timings.get("chat_s_estimated") or 0.0),
                                    "latency_s_total": float(trace_timings.get("latency_s_total") or (latency_ms / 1000.0) or 0.0),
                                }
                                active_live[idx] = current
                        _set_progress()
                    trace_steps = trace.get("steps") if trace_ok and isinstance(trace.get("steps"), list) else []
                    rag_metadata = {
                        "chunks_info": trace_chunks,
                        "max_score": trace_ctx.get("max_score") if isinstance(trace_ctx, dict) else None,
                        "chunks_count": len(trace_chunks),
                        "latency_ms": latency_ms,
                        "context_chars": trace_ctx.get("context_chars_used") if isinstance(trace_ctx, dict) else None,
                        "rag_queries": [{"query": (question or "")[:2000], "step": 0}],
                        "rag_timings": trace_timings if isinstance(trace_timings, dict) else None,
                    }
                    usage = {
                        "prompt_tokens": trace_tokens.get("prompt_tokens_estimated"),
                        "completion_tokens": trace_tokens.get("completion_tokens_estimated"),
                        "total_tokens": trace_tokens.get("total_tokens_estimated"),
                    }
                    output_tokens_final = (
                        output_tokens_exact
                        if output_tokens_exact is not None
                        else (int(usage.get("completion_tokens")) if usage.get("completion_tokens") is not None else None)
                    )
                    total_tokens_final = None
                    if output_tokens_exact is not None and prompt_tokens_exact is not None:
                        total_tokens_final = int(output_tokens_exact + prompt_tokens_exact)
                    elif usage.get("total_tokens") is not None:
                        try:
                            total_tokens_final = int(usage.get("total_tokens"))
                        except Exception:
                            total_tokens_final = None
                    latency_s = max(0.001, float(latency_ms) / 1000.0)
                    tokens_per_second_generated = (
                        (float(output_tokens_final) / latency_s) if output_tokens_final is not None else None
                    )
                    tokens_per_second_total = (
                        (float(total_tokens_final) / latency_s) if total_tokens_final is not None else None
                    )
                    rag_timings = rag_metadata.get("rag_timings") if isinstance(rag_metadata.get("rag_timings"), dict) else None
                    validation = validate_result(test, content, rag_metadata)
                    result = {
                        "_order": idx,
                        "test_id": test.get("id"),
                        "test_name": test.get("name"),
                        "platform": test.get("platform"),
                        "framework": test.get("framework"),
                        "difficulty": test.get("difficulty"),
                        "model": model,
                        "status": validation.get("status", "FAIL"),
                        "response_time_ms": latency_ms if latency_ms > 0 else elapsed_total_ms,
                        "latency_ms": latency_ms,
                        "rag_used": validation.get("rag_used", False),
                        "confidence_label": validation.get("confidence_label", ""),
                        "missing_concepts": validation.get("missing_concepts") or [],
                        "found_concepts": validation.get("found_concepts") or [],
                        "full_response": content or None,
                        "chunks_info": rag_metadata.get("chunks_info") or [],
                        "rag_queries": rag_metadata.get("rag_queries") or [],
                        "retrieved_chunks": validation.get("retrieved_chunks"),
                        "question": question,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "tokens_per_second_generated": tokens_per_second_generated,
                        "tokens_per_second_total": tokens_per_second_total,
                        "context_chars": rag_metadata.get("context_chars"),
                        "rag_timings": rag_timings,
                        "trace_steps": trace_steps,
                    }
                    if validation.get("failure_reason") is not None:
                        result["failure_reason"] = validation["failure_reason"]
                    return result
                except Exception as e:
                    _ERROR_LOG.exception("rag_tests_run single test")
                    _elapsed = int((time.time() - start_time) * 1000)
                    return {
                        "_order": idx,
                        "test_id": test.get("id"),
                        "test_name": test.get("name"),
                        "platform": test.get("platform"),
                        "framework": test.get("framework"),
                        "difficulty": test.get("difficulty"),
                        "model": model,
                        "status": "FAIL",
                        "response_time_ms": _elapsed,
                        "latency_ms": _elapsed,
                        "rag_used": False,
                        "confidence_label": "0/0",
                        "missing_concepts": test.get("expected_concepts") or [],
                        "found_concepts": [],
                        "full_response": None,
                        "chunks_info": [],
                        "rag_queries": [],
                        "retrieved_chunks": None,
                        "question": question,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "context_chars": None,
                        "failure_reason": str(e),
                        "error": str(e),
                    }

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rag-tests") as pool:
            futures: dict[Future[dict[str, Any]], int] = {}
            cancelled = False
            while True:
                with _rag_test_jobs_lock:
                    cancel_requested = bool(_rag_test_jobs.get(job_id, {}).get("cancel_requested"))
                if cancel_requested:
                    cancelled = True
                    for fut in list(futures.keys()):
                        fut.cancel()
                    break

                while launched < total and len(futures) < max_workers:
                    test = tests_to_run[launched]
                    with active_tests_lock:
                        active_tests[launched] = str(test.get("name") or test.get("id") or "")
                        active_live[launched] = {
                            "started_at_ms": int(time.time() * 1000),
                            "sse_enabled": False,
                            "sse_preview": "",
                            "sse_tokens_generated_est": 0,
                            "sse_token_tps_live": None,
                            "sse_token_tps_avg": None,
                            "current_step_timings": _default_live_timings(),
                        }
                    futures[pool.submit(_execute_single, launched, test)] = launched
                    launched += 1
                    _set_progress()

                if not futures:
                    break

                done, _ = wait(list(futures.keys()), timeout=0.25, return_when=FIRST_COMPLETED)
                if not done:
                    _set_progress()
                    continue
                for fut in done:
                    idx = futures.pop(fut, None)
                    if idx is None:
                        continue
                    with active_tests_lock:
                        active_tests.pop(idx, None)
                        active_live.pop(idx, None)
                    try:
                        result = fut.result()
                    except Exception as e:
                        _ERROR_LOG.exception("rag_tests_run future failed")
                        test = tests_to_run[idx]
                        result = {
                            "_order": idx,
                            "test_id": test.get("id"),
                            "test_name": test.get("name"),
                            "platform": test.get("platform"),
                            "framework": test.get("framework"),
                            "difficulty": test.get("difficulty"),
                            "model": model,
                            "status": "FAIL",
                            "response_time_ms": 0,
                            "latency_ms": 0,
                            "rag_used": False,
                            "confidence_label": "0/0",
                            "missing_concepts": test.get("expected_concepts") or [],
                            "found_concepts": [],
                            "full_response": None,
                            "chunks_info": [],
                            "rag_queries": [],
                            "retrieved_chunks": None,
                            "question": test.get("question") or "",
                            "prompt_tokens": None,
                            "completion_tokens": None,
                            "total_tokens": None,
                            "context_chars": None,
                            "failure_reason": str(e),
                            "error": str(e),
                        }
                    results.append(result)
                    completed += 1
                    if str(result.get("status") or "").upper() == "PASS":
                        passed += 1
                    else:
                        failed += 1
                    _set_progress(force_clear_sse=True)

            if cancelled:
                with _rag_test_jobs_lock:
                    job = _rag_test_jobs.get(job_id)
                    if job:
                        job["status"] = "cancelled"

        sorted_results = sorted(results, key=lambda r: int(r.get("_order", 0)))
        for r in sorted_results:
            r.pop("_order", None)

        with _rag_test_jobs_lock:
            if job_id in _rag_test_jobs and _rag_test_jobs[job_id]["status"] == "running":
                _rag_test_jobs[job_id]["status"] = "completed"
            _rag_test_jobs[job_id]["progress"]["passed"] = passed
            _rag_test_jobs[job_id]["progress"]["failed"] = failed
            _rag_test_jobs[job_id]["progress"]["pending"] = max(0, total - len(sorted_results))
            _rag_test_jobs[job_id]["progress"]["current_index"] = len(sorted_results)
            _rag_test_jobs[job_id]["progress"]["active_tests"] = []
            _rag_test_jobs[job_id]["progress"]["active_live"] = []
            _rag_test_jobs[job_id]["progress"]["active_count"] = 0
            _rag_test_jobs[job_id]["progress"]["current_test_name"] = ""
            _rag_test_jobs[job_id]["results"] = sorted_results
        try:
            runs_repo = get_rag_test_runs_repository()
            status = _rag_test_jobs.get(job_id, {}).get("status", "completed")
            runs_repo.add_run(
                run_id=job_id,
                model=model,
                status=status,
                total=total,
                passed=passed,
                failed=failed,
                results=sorted_results,
            )
        except Exception as e:
            _ERROR_LOG.warning("Failed to persist RAG test run: %s", e)


@rag_tests_bp.route("/rag-tests/run", methods=["POST"])
def rag_tests_run() -> Any:
    """Start RAG test run in background. Returns 202 with job_id. Poll GET /rag-tests/run/status/<job_id> for progress."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    body = request.get_json(force=True, silent=True) or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    try:
        requested_concurrency = int(body.get("concurrency") or 1)
    except Exception:
        requested_concurrency = 1
    concurrency = max(1, min(requested_concurrency, 8))
    test_ids = body.get("test_ids")
    filter_obj = body.get("filter") or {}
    root = get_root()
    all_tests = load_all(root)
    if test_ids:
        by_id = {t["id"]: t for t in all_tests}
        tests_to_run = [by_id[tid] for tid in test_ids if tid in by_id]
    elif filter_obj:
        tests_to_run = all_tests
        if filter_obj.get("platform"):
            tests_to_run = [t for t in tests_to_run if (t.get("platform") or "") == filter_obj["platform"]]
        if filter_obj.get("framework"):
            tests_to_run = [t for t in tests_to_run if (t.get("framework") or "") == filter_obj["framework"]]
        if filter_obj.get("difficulty"):
            tests_to_run = [t for t in tests_to_run if (t.get("difficulty") or "") == filter_obj["difficulty"]]
    else:
        tests_to_run = all_tests
    if not tests_to_run:
        return jsonify({"results": [], "message": "No tests to run"})
    collection_name = (body.get("collection_name") or "").strip()
    collection_source = "request"
    if not collection_name:
        try:
            repo = get_settings_repository()
            proxy_settings = load_proxy_settings(repo)
            resolved, source = resolve_rag_collection(
                request_collection=None,
                settings_repo=repo,
                proxy_settings=proxy_settings,
                app_key="rag_collection",
            )
        except Exception:
            resolved, source = None, "default"
        collection_name = str(resolved or "").strip()
        collection_source = source
        if not collection_name:
            names = _get_qdrant_collection_names()
            if not names:
                return jsonify({
                    "error": "No Qdrant collections. Create one in Crawler / RAG then come back.",
                }), 400
            collection_name = names[0]
            collection_source = "qdrant.first_collection"
    prompt_name = (body.get("prompt_name") or "").strip() or None
    temperature_raw = body.get("temperature")
    top_k_raw = body.get("top_k")
    try:
        temperature = float(temperature_raw) if temperature_raw is not None else None
    except (TypeError, ValueError):
        temperature = None
    try:
        top_k = float(top_k_raw) if top_k_raw is not None else None
    except (TypeError, ValueError):
        top_k = None
    testing_disable_rerank = bool(body.get("testing_disable_rerank", False))
    job_id = str(uuid.uuid4())[:12]
    with _rag_test_jobs_lock:
        _rag_test_jobs[job_id] = {
            "status": "running",
            "cancel_requested": False,
            "progress": {
                "current_index": 0,
                "total": len(tests_to_run),
                "current_test_name": "",
                "active_tests": [],
                "active_live": [],
                "active_count": 0,
                "max_concurrency": concurrency,
                "passed": 0,
                "failed": 0,
                "pending": len(tests_to_run),
                "sse_enabled": False,
                "sse_preview": "",
                "sse_tokens_generated_est": 0,
                "sse_token_tps_live": None,
                "sse_token_tps_avg": None,
                "current_step_timings": {
                    "embed_s": 0.0,
                    "search_s": 0.0,
                    "rerank_s": 0.0,
                    "total_rag_s": 0.0,
                    "chat_s_estimated": 0.0,
                    "latency_s_total": 0.0,
                },
            },
            "results": [],
            "error": None,
        }
    thread = threading.Thread(
        target=_rag_tests_run_worker,
        args=(
            job_id,
            current_app.app_context(),
            tests_to_run,
            model,
            collection_name,
            prompt_name,
            temperature,
            top_k,
            concurrency,
            testing_disable_rerank,
        ),
        daemon=True,
    )
    thread.start()
    return jsonify({
        "job_id": job_id,
        "collection_name": collection_name,
        "prompt_name": prompt_name,
        "temperature": temperature,
        "top_k": top_k,
        "concurrency": concurrency,
        "collection_source": collection_source,
        "testing_disable_rerank": testing_disable_rerank,
    }), 202


@rag_tests_bp.route("/rag-tests/run/status/<job_id>", methods=["GET"])
def rag_tests_run_status(job_id: str) -> Any:
    """Get run progress and results. status: running | completed | cancelled."""
    with _rag_test_jobs_lock:
        job = _rag_test_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "results": job["results"],
        "error": job.get("error"),
    })


@rag_tests_bp.route("/rag-tests/run/cancel/<job_id>", methods=["POST"])
def rag_tests_run_cancel(job_id: str) -> Any:
    """Request cancel; runner will stop after current test."""
    with _rag_test_jobs_lock:
        job = _rag_test_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "running":
        return jsonify({"message": "Job not running", "status": job["status"]})
    with _rag_test_jobs_lock:
        _rag_test_jobs[job_id]["cancel_requested"] = True
    return jsonify({"message": "Cancel requested", "job_id": job_id})


@rag_tests_bp.route("/rag-tests", methods=["POST"])
def rag_tests_create() -> Any:
    """Create a new RAG test: body { name, question, concepts[], platform, framework, difficulty, concept_mode?, min_os?, notes? }. Writes .md file."""
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if get_root is None:
        return jsonify({"error": "RAG tests module not available"}), 500
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or body.get("question") or "Untitled test")[:200].strip()
    question = (body.get("question") or "").strip()
    concepts = body.get("concepts") or body.get("expected_concepts") or []
    if isinstance(concepts, str):
        concepts = [c.strip() for c in concepts.split("\n") if c.strip()]
    concepts = _normalize_concepts(list(concepts))
    platform = (body.get("platform") or "iOS").strip()
    framework = (body.get("framework") or "SwiftUI").strip()
    difficulty = (body.get("difficulty") or "intermediate").strip()
    concept_mode = (body.get("concept_mode") or "all").strip().lower()
    if concept_mode not in ("any", "all"):
        concept_mode = "all"
    rag_strict = bool(body.get("rag_strict"))
    min_os = (body.get("min_os") or "").strip()
    notes = (body.get("notes") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    slug = re.sub(r"[^\w\s-]", "", name).strip()
    slug = re.sub(r"[-\s]+", "_", slug).lower()[:80] or "test"
    root = Path(get_root())
    platform_dir = root / platform.lower().replace(" ", "_")
    framework_dir = platform_dir / framework.lower().replace(" ", "_")
    framework_dir.mkdir(parents=True, exist_ok=True)
    path = framework_dir / f"{slug}.md"
    if path.exists():
        n = 1
        while (framework_dir / f"{slug}_{n}.md").exists():
            n += 1
        path = framework_dir / f"{slug}_{n}.md"
        slug = f"{slug}_{n}"

    content = _rag_tests_build_md(
        name, question, concepts, platform, framework, difficulty, concept_mode, rag_strict, min_os, notes
    )
    path.write_text(content, encoding="utf-8")
    test_id = str(path.relative_to(root)).replace(".md", "").replace("/", "_").replace("\\", "_")
    return jsonify({"id": test_id, "file_path": str(path.relative_to(root)), "message": "Test created"}), 201




__all__ = ["rag_tests_bp"]
