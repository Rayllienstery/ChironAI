"""Background workers for RAG test execution routes."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from flask import current_app

from application.rag_tests.metrics import normalize_rag_test_result
from application.rag_tests.runner import (
    build_proxy_chat_payload,
    build_rag_test_error_result,
    build_rag_test_result,
    build_test_retrieval_query,
    rag_tests_retrieval_preset,
)
from infrastructure.database import get_rag_test_runs_repository

_ERROR_LOG = None
_rag_test_jobs = None
_rag_test_jobs_lock = None
_get_rag_tests_module = None
_find_trace_by_client_request_id = None
_find_response_artifacts_for_request_id = None
_live_rag_step_timings = None
_route_build_rag_context = None
_route_get_rag_answer_params = None


def _ensure_route_state() -> None:
    global _ERROR_LOG
    global _find_response_artifacts_for_request_id
    global _find_trace_by_client_request_id
    global _get_rag_tests_module
    global _live_rag_step_timings
    global _rag_test_jobs
    global _rag_test_jobs_lock
    global _route_build_rag_context
    global _route_get_rag_answer_params

    from api.http import rag_tests_routes as routes

    _ERROR_LOG = routes._ERROR_LOG
    _rag_test_jobs = routes._rag_test_jobs
    _rag_test_jobs_lock = routes._rag_test_jobs_lock
    _get_rag_tests_module = routes._get_rag_tests_module
    _find_trace_by_client_request_id = routes._find_trace_by_client_request_id
    _find_response_artifacts_for_request_id = routes._find_response_artifacts_for_request_id
    _live_rag_step_timings = routes._live_rag_step_timings
    _route_get_rag_answer_params = routes.get_rag_answer_params
    _route_build_rag_context = routes.build_rag_context
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
    strict_mode: bool = False,
    provider_id: str | None = None,
) -> None:
    """Background worker: run tests concurrently, update progress, respect cancel."""
    _ensure_route_state()
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
                        provider_id=provider_id,
                        collection_name=collection_name,
                        client_request_id=request_id,
                        prompt_name=prompt_name,
                        temperature=temperature,
                        top_k=top_k,
                        testing_disable_rerank=testing_disable_rerank,
                        strict_mode=strict_mode,
                    )
                    with rag_tests_retrieval_preset():
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
                        return build_rag_test_error_result(
                            test=test,
                            model=model,
                            provider_id=provider_id,
                            error=err,
                            response_time_ms=elapsed_ms,
                            order=idx,
                            strict_mode=strict_mode,
                        )

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
                    response_artifacts = _find_response_artifacts_for_request_id(request_id) or {}
                    final_content = str(response_artifacts.get("final_content") or "")
                    if final_content.strip():
                        content = final_content
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
                        if trace_resp.get("eval_count") is not None:
                            output_tokens_exact = int(trace_resp.get("eval_count"))
                        elif trace_resp.get("ollama_eval_count") is not None:
                            output_tokens_exact = int(trace_resp.get("ollama_eval_count"))
                    except Exception:
                        output_tokens_exact = None
                    try:
                        if trace_resp.get("prompt_eval_count") is not None:
                            prompt_tokens_exact = int(trace_resp.get("prompt_eval_count"))
                        elif trace_resp.get("ollama_prompt_eval_count") is not None:
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
                    validation = validate_result(test, content, rag_metadata, strict_mode=strict_mode)
                    result = build_rag_test_result(
                        test=test,
                        model=model,
                        provider_id=provider_id,
                        content=content,
                        rag_metadata=rag_metadata,
                        validation=validation,
                        response_time_ms=latency_ms if latency_ms > 0 else elapsed_total_ms,
                        latency_ms=latency_ms,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        total_tokens=usage.get("total_tokens"),
                        tokens_per_second_generated=tokens_per_second_generated,
                        tokens_per_second_total=tokens_per_second_total,
                        context_chars=rag_metadata.get("context_chars"),
                        rag_timings=rag_timings,
                        trace_steps=trace_steps,
                        order=idx,
                    )
                    return normalize_rag_test_result(result)
                except Exception as e:
                    _ERROR_LOG.exception("rag_tests_run single test")
                    _elapsed = int((time.time() - start_time) * 1000)
                    return build_rag_test_error_result(
                        test=test,
                        model=model,
                        provider_id=provider_id,
                        error=e,
                        response_time_ms=_elapsed,
                        order=idx,
                        strict_mode=strict_mode,
                    )

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
                        result = build_rag_test_error_result(
                            test=test,
                            model=model,
                            provider_id=provider_id,
                            error=e,
                            response_time_ms=0,
                            order=idx,
                            strict_mode=strict_mode,
                        )
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

        sorted_results = [normalize_rag_test_result(r) for r in sorted(results, key=lambda r: int(r.get("_order", 0)))]
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
                provider_id=provider_id,
                model=model,
                status=status,
                total=total,
                passed=passed,
                failed=failed,
                results=sorted_results,
            )
        except Exception as e:
            _ERROR_LOG.warning("Failed to persist RAG test run: %s", e)


def _build_retrieval_v2_result(
    *,
    test: dict[str, Any],
    retrieval_query: str,
    ctx: Any,
    rag_timings: dict[str, Any] | None,
    elapsed_ms: int,
    order: int,
) -> dict[str, Any]:
    chunks_info = list(getattr(ctx, "chunks_info", None) or [])
    retrieval_skipped = bool(getattr(ctx, "retrieval_skipped", False))
    chunks_count = len(chunks_info)
    status = "skipped" if retrieval_skipped else ("retrieved" if chunks_count > 0 else "empty")
    return {
        "test_id": test.get("id"),
        "test_name": test.get("name"),
        "question": test.get("question") or "",
        "platform": test.get("platform"),
        "framework": test.get("framework"),
        "difficulty": test.get("difficulty"),
        "status": status,
        "retrieval_query": retrieval_query[:2000],
        "retrieval_used": chunks_count > 0,
        "retrieval_skipped": retrieval_skipped,
        "chunks_info": chunks_info,
        "chunks_count": chunks_count,
        "rag_timings": rag_timings or {},
        "trace_steps": list(getattr(ctx, "rag_trace", None) or []),
        "max_score": float(getattr(ctx, "max_score", 0.0) or 0.0),
        "context_chars": len(getattr(ctx, "context_text", "") or ""),
        "response_time_ms": elapsed_ms,
        "latency_ms": elapsed_ms,
        "_order": order,
    }


def _build_retrieval_v2_error_result(
    *,
    test: dict[str, Any],
    retrieval_query: str,
    error: Any,
    elapsed_ms: int,
    order: int,
) -> dict[str, Any]:
    return {
        "test_id": test.get("id"),
        "test_name": test.get("name"),
        "question": test.get("question") or "",
        "platform": test.get("platform"),
        "framework": test.get("framework"),
        "difficulty": test.get("difficulty"),
        "status": "error",
        "retrieval_query": retrieval_query[:2000],
        "retrieval_used": False,
        "retrieval_skipped": False,
        "chunks_info": [],
        "chunks_count": 0,
        "rag_timings": {},
        "trace_steps": [],
        "max_score": 0.0,
        "context_chars": 0,
        "response_time_ms": elapsed_ms,
        "latency_ms": elapsed_ms,
        "failure_reason": str(error),
        "error": str(error),
        "_order": order,
    }


def _rag_tests_v2_run_worker(
    job_id: str,
    app_context: Any,
    tests_to_run: list[dict[str, Any]],
    collection_name: str,
    *,
    top_k: float | None = None,
    concurrency: int = 1,
    testing_disable_rerank: bool = False,
) -> None:
    _ensure_route_state()
    with app_context:
        max_workers = max(1, min(int(concurrency or 1), 8))
        total = len(tests_to_run)
        results: list[dict[str, Any]] = []
        retrieved = 0
        empty = 0
        skipped = 0
        errors = 0
        completed = 0
        launched = 0
        active_tests: dict[int, str] = {}
        active_tests_lock = threading.Lock()

        def _set_progress() -> None:
            with active_tests_lock:
                active_snapshot = dict(active_tests)
            with _rag_test_jobs_lock:
                job = _rag_test_jobs.get(job_id)
                if not job:
                    return
                active_count = len(active_snapshot)
                job["progress"] = {
                    "current_index": completed + active_count,
                    "total": total,
                    "current_test_name": next(iter(active_snapshot.values()), ""),
                    "active_tests": list(active_snapshot.values()),
                    "active_count": active_count,
                    "max_concurrency": max_workers,
                    "retrieved": retrieved,
                    "empty": empty,
                    "skipped": skipped,
                    "errors": errors,
                    "pending": max(0, total - completed - active_count),
                }
                job["results"] = [dict(r) for r in sorted(results, key=lambda r: int(r.get("_order", 0)))]

        def _execute_single(idx: int, test: dict[str, Any]) -> dict[str, Any]:
            start_time = time.time()
            retrieval_query = build_test_retrieval_query(test)
            try:
                params, deps = _route_get_rag_answer_params(
                    collection_name=collection_name,
                    prompt_name="system_senior_ios_assistant_rag_tests",
                )
                rerank_client = None if testing_disable_rerank else deps.rerank_client
                with rag_tests_retrieval_preset():
                    ctx, timings = _route_build_rag_context(
                        retrieval_query,
                        deps.rag_repo,
                        deps.embed_provider,
                        rerank_client,
                        params.context_chunk_chars,
                        params.context_total_chars,
                        top_k=max(1, int(round(float(top_k)))) if top_k is not None else None,
                        rag_required_keywords=None,
                        trigger_threshold=None,
                        force_rag=True,
                    )
                elapsed_ms = int((time.time() - start_time) * 1000)
                return _build_retrieval_v2_result(
                    test=test,
                    retrieval_query=retrieval_query,
                    ctx=ctx,
                    rag_timings=timings,
                    elapsed_ms=elapsed_ms,
                    order=idx,
                )
            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                return _build_retrieval_v2_error_result(
                    test=test,
                    retrieval_query=retrieval_query,
                    error=e,
                    elapsed_ms=elapsed_ms,
                    order=idx,
                )

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rag-tests-v2") as pool:
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
                    try:
                        row = fut.result()
                    except Exception as e:
                        row = _build_retrieval_v2_error_result(
                            test=tests_to_run[idx],
                            retrieval_query=build_test_retrieval_query(tests_to_run[idx]),
                            error=e,
                            elapsed_ms=0,
                            order=idx,
                        )
                    results.append(row)
                    completed += 1
                    status = str(row.get("status") or "")
                    if status == "retrieved":
                        retrieved += 1
                    elif status == "empty":
                        empty += 1
                    elif status == "skipped":
                        skipped += 1
                    else:
                        errors += 1
                    _set_progress()

            if cancelled:
                with _rag_test_jobs_lock:
                    job = _rag_test_jobs.get(job_id)
                    if job:
                        job["status"] = "cancelled"

        sorted_results = [dict(r) for r in sorted(results, key=lambda r: int(r.get("_order", 0)))]
        for r in sorted_results:
            r.pop("_order", None)

        with _rag_test_jobs_lock:
            if job_id in _rag_test_jobs and _rag_test_jobs[job_id]["status"] == "running":
                _rag_test_jobs[job_id]["status"] = "completed"
            _rag_test_jobs[job_id]["progress"]["retrieved"] = retrieved
            _rag_test_jobs[job_id]["progress"]["empty"] = empty
            _rag_test_jobs[job_id]["progress"]["skipped"] = skipped
            _rag_test_jobs[job_id]["progress"]["errors"] = errors
            _rag_test_jobs[job_id]["progress"]["pending"] = max(0, total - len(sorted_results))
            _rag_test_jobs[job_id]["progress"]["current_index"] = len(sorted_results)
            _rag_test_jobs[job_id]["progress"]["active_tests"] = []
            _rag_test_jobs[job_id]["progress"]["active_count"] = 0
            _rag_test_jobs[job_id]["progress"]["current_test_name"] = ""
            _rag_test_jobs[job_id]["results"] = sorted_results

__all__ = [
    "_build_retrieval_v2_error_result",
    "_build_retrieval_v2_result",
    "_rag_tests_run_worker",
    "_rag_tests_v2_run_worker",
]

