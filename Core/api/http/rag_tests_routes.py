"""
Dedicated Flask routes for RAG tests management and execution.

Split from api.http.webui_routes to keep WebUI composition slim and make
RAG tests orchestration independently maintainable.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request
from rag_service.application.params import get_rag_answer_params as _get_rag_answer_params
from rag_service.application.use_cases import build_rag_context as _build_rag_context

from api.http.proxy_trace import get_current_trace, get_response_artifacts, recent_proxy_traces
from api.http.rag_tests_workers import _rag_tests_run_worker, _rag_tests_v2_run_worker
from application.rag.proxy_settings_contract import load_proxy_settings, resolve_rag_collection
from application.rag_tests.authoring import (
    build_rag_test_markdown as _rag_tests_build_md,
)
from application.rag_tests.authoring import (
    normalize_concepts as _normalize_concepts,
)
from application.rag_tests.metrics import (
    normalize_rag_test_result,
    normalize_rag_test_run,
)
from core.contracts.webui_api import WEBUI_URL_PREFIX
from infrastructure.database import get_rag_test_runs_repository, get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from infrastructure.qdrant.collection_names import list_collection_names

rag_tests_bp = Blueprint("rag_tests", __name__, url_prefix=WEBUI_URL_PREFIX)
_ERROR_LOG = get_webui_error_logger()
get_rag_answer_params = _get_rag_answer_params
build_rag_context = _build_rag_context


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


def _find_response_artifacts_for_request_id(request_id: str) -> dict[str, Any] | None:
    rid = str(request_id or "").strip()
    if not rid:
        return None
    artifacts = get_response_artifacts(rid)
    if isinstance(artifacts, dict):
        return artifacts
    trace = _find_trace_by_client_request_id(rid) or {}
    trace_id = str(trace.get("trace_id") or "").strip() if isinstance(trace, dict) else ""
    if trace_id:
        artifacts = get_response_artifacts(trace_id)
        if isinstance(artifacts, dict):
            return artifacts
    return None


def _select_tests_to_run(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    get_root, _, load_all, _, _ = _get_rag_tests_module()
    if load_all is None or get_root is None:
        return [], "RAG tests module not available"
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
    return tests_to_run, None


def _resolve_collection_name(requested_collection_name: str) -> tuple[str | None, str | None, str | None]:
    collection_name = str(requested_collection_name or "").strip()
    collection_source = "request"
    if collection_name:
        return collection_name, collection_source, None
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
    if collection_name:
        return collection_name, collection_source, None
    names = list_collection_names()
    if not names:
        return None, None, "No Qdrant collections. Create one in Crawler / RAG then come back."
    return names[0], "qdrant.first_collection", None


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
    get_root, list_filters, load_all, _, _ = _get_rag_tests_module()
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
        provider_id = (request.args.get("provider_id") or "").strip() or None
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        status = (request.args.get("status") or "").strip() or None
        runs = repo.get_runs(
            limit=limit,
            offset=offset,
            provider_id=provider_id,
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
        provider_id = (request.args.get("provider_id") or "").strip() or None
        model = (request.args.get("model") or "").strip() or None
        from_date = (request.args.get("from_date") or "").strip() or None
        to_date = (request.args.get("to_date") or "").strip() or None
        summary = repo.get_runs_summary(
            limit=limit,
            provider_id=provider_id,
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
        return jsonify(normalize_rag_test_run(run))
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_run_detail")
        return jsonify({"error": str(e)}), 500


@rag_tests_bp.route("/rag-tests/runs", methods=["DELETE"])
def rag_tests_runs_delete() -> Any:
    """Delete past RAG test runs by selected ids or history filter presets."""
    try:
        repo = get_rag_test_runs_repository()
        body = request.get_json(silent=True) or {}
        run_ids_raw = body.get("run_ids")
        run_ids = [str(v).strip() for v in (run_ids_raw or []) if str(v).strip()] if isinstance(run_ids_raw, list) else []
        delete_cancelled = bool(body.get("delete_cancelled"))
        delete_low_pass = bool(body.get("delete_low_pass"))
        max_pass_rate_pct_raw = body.get("max_pass_rate_pct", 25)
        try:
            max_pass_rate_pct = float(max_pass_rate_pct_raw)
        except (TypeError, ValueError):
            max_pass_rate_pct = 25.0

        deleted = 0
        if run_ids:
            deleted = repo.delete_runs(run_ids=run_ids)
        elif delete_cancelled:
            deleted = repo.delete_runs(status="cancelled")
        elif delete_low_pass:
            deleted = repo.delete_runs(max_pass_rate_pct=max_pass_rate_pct)
        else:
            return jsonify({"error": "No delete criteria provided"}), 400

        return jsonify({"status": "ok", "deleted": deleted})
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_runs_delete")
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
        run = normalize_rag_test_run(run)
    except Exception as e:
        _ERROR_LOG.exception("rag_tests_export_run")
        return jsonify({"error": str(e)}), 500
    created = run.get("created_at") or ""
    safe_date = created.replace(":", "-").replace(" ", "_")[:19] if created else "run"
    filename = f"rag-test-run-{run_id}-{safe_date}.{export_format}"
    if export_format == "csv":
        import csv
        import io
        rows = [[
            "test_id",
            "test_name",
            "platform",
            "framework",
            "status",
            "response_time_ms",
            "rag_used",
            "retrieval_used",
            "grounding_overlap",
            "strict_rag_ok",
            "strict_mode",
            "strict_quote_ok",
            "strict_quote_reason",
            "metrics_version",
            "evaluation_method_version",
            "confidence_label",
            "question",
            "error",
        ]]
        for r in (run.get("results") or []):
            r = normalize_rag_test_result(r)
            rows.append([
                r.get("test_id") or "",
                r.get("test_name") or "",
                r.get("platform") or "",
                r.get("framework") or "",
                r.get("status") or "",
                str(r.get("response_time_ms") or ""),
                "yes" if r.get("rag_used") else "no",
                "yes" if r.get("retrieval_used") else "no",
                "" if r.get("grounding_overlap") is None else ("yes" if r.get("grounding_overlap") else "no"),
                "" if r.get("strict_rag_ok") is None else ("yes" if r.get("strict_rag_ok") else "no"),
                "yes" if r.get("strict_mode") else "no",
                "" if r.get("strict_quote_ok") is None else ("yes" if r.get("strict_quote_ok") else "no"),
                r.get("strict_quote_reason") or "",
                r.get("metrics_version") or "",
                r.get("evaluation_method_version") or "",
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


@rag_tests_bp.route("/rag-tests/run", methods=["POST"])
def rag_tests_run() -> Any:
    """Start RAG test run in background. Returns 202 with job_id. Poll GET /rag-tests/run/status/<job_id> for progress."""
    body = request.get_json(force=True, silent=True) or {}
    provider_id = (body.get("provider_id") or "").strip() or None
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    try:
        requested_concurrency = int(body.get("concurrency") or 1)
    except Exception:
        requested_concurrency = 1
    concurrency = max(1, min(requested_concurrency, 8))
    tests_to_run, select_error = _select_tests_to_run(body)
    if select_error:
        return jsonify({"error": select_error}), 500
    if not tests_to_run:
        return jsonify({"results": [], "message": "No tests to run"})
    collection_name, collection_source, collection_error = _resolve_collection_name(body.get("collection_name") or "")
    if collection_error:
        return jsonify({"error": collection_error}), 400
    prompt_name = (body.get("prompt_name") or "").strip() or "system_senior_ios_assistant_rag_tests"
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
    strict_mode = bool(body.get("strict_mode", False))
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
            "strict_mode": strict_mode,
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
            strict_mode,
        ),
        kwargs={"provider_id": provider_id},
        daemon=True,
    )
    thread.start()
    return jsonify({
        "job_id": job_id,
        "collection_name": collection_name,
        "provider_id": provider_id,
        "prompt_name": prompt_name,
        "temperature": temperature,
        "top_k": top_k,
        "concurrency": concurrency,
        "collection_source": collection_source,
        "testing_disable_rerank": testing_disable_rerank,
        "strict_mode": strict_mode,
    }), 202


@rag_tests_bp.route("/rag-tests-v2/run", methods=["POST"])
def rag_tests_v2_run() -> Any:
    """Start retrieval-only RAG test run in background."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        requested_concurrency = int(body.get("concurrency") or 1)
    except Exception:
        requested_concurrency = 1
    concurrency = max(1, min(requested_concurrency, 8))
    tests_to_run, select_error = _select_tests_to_run(body)
    if select_error:
        return jsonify({"error": select_error}), 500
    if not tests_to_run:
        return jsonify({"results": [], "message": "No tests to run"})
    collection_name, collection_source, collection_error = _resolve_collection_name(body.get("collection_name") or "")
    if collection_error:
        return jsonify({"error": collection_error}), 400
    top_k_raw = body.get("top_k")
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
                "active_count": 0,
                "max_concurrency": concurrency,
                "retrieved": 0,
                "empty": 0,
                "skipped": 0,
                "errors": 0,
                "pending": len(tests_to_run),
            },
            "results": [],
            "error": None,
            "mode": "retrieval_only",
        }
    thread = threading.Thread(
        target=_rag_tests_v2_run_worker,
        args=(
            job_id,
            current_app.app_context(),
            tests_to_run,
            str(collection_name),
        ),
        kwargs={
            "top_k": top_k,
            "concurrency": concurrency,
            "testing_disable_rerank": testing_disable_rerank,
        },
        daemon=True,
    )
    thread.start()
    return jsonify({
        "job_id": job_id,
        "collection_name": collection_name,
        "top_k": top_k,
        "concurrency": concurrency,
        "collection_source": collection_source,
        "testing_disable_rerank": testing_disable_rerank,
        "mode": "retrieval_only",
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


@rag_tests_bp.route("/rag-tests-v2/run/status/<job_id>", methods=["GET"])
def rag_tests_v2_run_status(job_id: str) -> Any:
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
        "mode": job.get("mode") or "retrieval_only",
    })


@rag_tests_bp.route("/rag-tests-v2/run/cancel/<job_id>", methods=["POST"])
def rag_tests_v2_run_cancel(job_id: str) -> Any:
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
