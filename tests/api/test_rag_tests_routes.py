from __future__ import annotations

import json
from types import SimpleNamespace

from flask import Flask, Response, request


def test_rag_tests_worker_uses_v1_chat_completions_payload_parity(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes

    captured: dict[str, object] = {}

    app = Flask(__name__)

    @app.route("/v1/chat/completions", methods=["POST"])
    def _v1_chat() -> Response:
        body = request.get_json(silent=True) or {}
        captured.clear()
        captured.update(body)

        def _gen():
            yield f"data: {json.dumps({'choices': [{'delta': {'content': 'ok'}}]})}\n\n"
            yield "data: [DONE]\n\n"

        return Response(_gen(), mimetype="text/event-stream")

    def _validate_result(_test, _content, _metadata, **_kwargs):
        return {
            "status": "PASS",
            "rag_used": True,
            "confidence_label": "1/1 concepts found",
            "missing_concepts": [],
            "found_concepts": ["x"],
        }

    monkeypatch.setattr(
        routes,
        "_get_rag_tests_module",
        lambda: (lambda: "", None, None, None, _validate_result),
    )

    job_id = "job123"
    routes._rag_test_jobs[job_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": {},
        "results": [],
        "error": None,
    }

    with app.app_context():
        routes._rag_tests_run_worker(
            job_id=job_id,
            app_context=app.app_context(),
            tests_to_run=[{"id": "t1", "name": "T1", "question": "Q1", "expected_concepts": []}],
            model="llama3",
            collection_name="ios-docs",
            prompt_name="system_senior_ios_assistant_v1",
            temperature=0.0,
            top_k=8,
            concurrency=1,
            testing_disable_rerank=True,
            strict_mode=True,
        )

    assert captured.get("model") == "llama3"
    assert captured.get("collection_name") == "ios-docs"
    assert captured.get("prompt_name") == "system_senior_ios_assistant_v1"
    assert captured.get("top_k") == 8.0
    assert captured.get("testing_disable_rerank") is True
    assert captured.get("strict_mode") is True
    assert "RAG QUOTE" in captured.get("messages", [{}])[0].get("content", "")


def test_rag_tests_worker_prefers_final_content_from_response_artifacts(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes

    observed: dict[str, object] = {}
    app = Flask(__name__)

    @app.route("/v1/chat/completions", methods=["POST"])
    def _v1_chat() -> Response:
        def _gen():
            yield f"data: {json.dumps({'choices': [{'delta': {'content': 'thinking text'}}]})}\n\n"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': ' final answer'}}]})}\n\n"
            yield "data: [DONE]\n\n"

        return Response(_gen(), mimetype="text/event-stream")

    def _validate_result(_test, content, _metadata, **_kwargs):
        observed["content"] = content
        return {
            "status": "PASS",
            "rag_used": True,
            "confidence_label": "1/1 concepts found",
            "missing_concepts": [],
            "found_concepts": ["x"],
        }

    monkeypatch.setattr(
        routes,
        "_get_rag_tests_module",
        lambda: (lambda: "", None, None, None, _validate_result),
    )
    monkeypatch.setattr(
        routes,
        "_find_response_artifacts_for_request_id",
        lambda _rid: {"final_content": "final answer"},
    )

    job_id = "job-final-content"
    routes._rag_test_jobs[job_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": {},
        "results": [],
        "error": None,
    }

    with app.app_context():
        routes._rag_tests_run_worker(
            job_id=job_id,
            app_context=app.app_context(),
            tests_to_run=[{"id": "t1", "name": "T1", "question": "Q1", "expected_concepts": []}],
            model="llama3",
            collection_name="ios-docs",
            prompt_name="system_senior_ios_assistant_v1",
            temperature=0.0,
            top_k=8,
            concurrency=1,
            testing_disable_rerank=True,
            strict_mode=False,
        )

    assert observed["content"] == "final answer"


def test_rag_tests_worker_falls_back_to_merged_sse_content_without_response_artifacts(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes

    observed: dict[str, object] = {}
    app = Flask(__name__)

    @app.route("/v1/chat/completions", methods=["POST"])
    def _v1_chat() -> Response:
        def _gen():
            yield f"data: {json.dumps({'choices': [{'delta': {'content': 'thinking text'}}]})}\n\n"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': ' final answer'}}]})}\n\n"
            yield "data: [DONE]\n\n"

        return Response(_gen(), mimetype="text/event-stream")

    def _validate_result(_test, content, _metadata, **_kwargs):
        observed["content"] = content
        return {
            "status": "PASS",
            "rag_used": True,
            "confidence_label": "1/1 concepts found",
            "missing_concepts": [],
            "found_concepts": ["x"],
        }

    monkeypatch.setattr(
        routes,
        "_get_rag_tests_module",
        lambda: (lambda: "", None, None, None, _validate_result),
    )
    monkeypatch.setattr(routes, "_find_response_artifacts_for_request_id", lambda _rid: None)

    job_id = "job-merged-fallback"
    routes._rag_test_jobs[job_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": {},
        "results": [],
        "error": None,
    }

    with app.app_context():
        routes._rag_tests_run_worker(
            job_id=job_id,
            app_context=app.app_context(),
            tests_to_run=[{"id": "t1", "name": "T1", "question": "Q1", "expected_concepts": []}],
            model="llama3",
            collection_name="ios-docs",
            prompt_name="system_senior_ios_assistant_v1",
            temperature=0.0,
            top_k=8,
            concurrency=1,
            testing_disable_rerank=True,
            strict_mode=False,
        )

    assert observed["content"] == "thinking text final answer"


def test_rag_tests_v2_worker_uses_build_rag_context_without_chat_completion(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes

    observed: dict[str, object] = {"chat_called": 0}
    app = Flask(__name__)

    @app.route("/v1/chat/completions", methods=["POST"])
    def _v1_chat() -> Response:
        observed["chat_called"] = int(observed["chat_called"]) + 1
        return Response("unexpected", mimetype="text/plain")

    monkeypatch.setattr(
        routes,
        "get_rag_answer_params",
        lambda **_kwargs: (
            SimpleNamespace(context_chunk_chars=4000, context_total_chars=12000),
            SimpleNamespace(rag_repo=object(), embed_provider=object(), rerank_client="reranker"),
        ),
    )

    def _fake_build_rag_context(
        query,
        _rag_repo,
        _embed_provider,
        rerank_client,
        _context_chunk_chars,
        _context_total_chars,
        **_kwargs,
    ):
        observed["query"] = query
        observed["rerank_client"] = rerank_client
        return (
            SimpleNamespace(
                chunks_info=[{"text": "hit one", "score": 0.91}],
                retrieval_skipped=False,
                rag_trace=[{"label": "embed_search_pass1", "detail": "ok"}],
                max_score=0.91,
                context_text="hit one",
            ),
            {"embed_s": 0.01, "search_s": 0.02, "total_rag_s": 0.03},
        )

    monkeypatch.setattr(routes, "build_rag_context", _fake_build_rag_context)

    job_id = "job-v2-worker"
    routes._rag_test_jobs[job_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": {},
        "results": [],
        "error": None,
        "mode": "retrieval_only",
    }

    with app.app_context():
        routes._rag_tests_v2_run_worker(
            job_id,
            app.app_context(),
            [
                {
                    "id": "t1",
                    "name": "Observation",
                    "question": "How do I use Observation with SwiftUI?",
                    "platform": "iOS",
                    "framework": "SwiftUI",
                    "expected_concepts": ["@Observable"],
                }
            ],
            "ios-docs",
            top_k=8,
            concurrency=1,
            testing_disable_rerank=False,
        )

    assert "Relevant terms:" in str(observed["query"])
    assert "@Observable" in str(observed["query"])
    assert observed["rerank_client"] == "reranker"
    assert observed["chat_called"] == 0
    assert routes._rag_test_jobs[job_id]["results"][0]["status"] == "retrieved"


def test_rag_tests_v2_worker_applies_preset_and_can_disable_rerank(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes
    from rag_service.config import get_retrieval_bool

    observed: dict[str, object] = {}
    app = Flask(__name__)

    monkeypatch.setattr(
        routes,
        "get_rag_answer_params",
        lambda **_kwargs: (
            SimpleNamespace(context_chunk_chars=4000, context_total_chars=12000),
            SimpleNamespace(rag_repo=object(), embed_provider=object(), rerank_client="reranker"),
        ),
    )

    def _fake_build_rag_context(
        _query,
        _rag_repo,
        _embed_provider,
        rerank_client,
        _context_chunk_chars,
        _context_total_chars,
        **_kwargs,
    ):
        observed["rerank_client"] = rerank_client
        observed["coverage_gate_enabled"] = get_retrieval_bool("coverage_gate_enabled", False)
        observed["coverage_retry_enabled"] = get_retrieval_bool(
            "coverage_retry_supplemental_search_enabled", False
        )
        return (
            SimpleNamespace(
                chunks_info=[],
                retrieval_skipped=False,
                rag_trace=[],
                max_score=0.0,
                context_text="",
            ),
            {"total_rag_s": 0.01},
        )

    monkeypatch.setattr(routes, "build_rag_context", _fake_build_rag_context)

    job_id = "job-v2-rerank"
    routes._rag_test_jobs[job_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": {},
        "results": [],
        "error": None,
        "mode": "retrieval_only",
    }

    with app.app_context():
        routes._rag_tests_v2_run_worker(
            job_id,
            app.app_context(),
            [{"id": "t1", "name": "T1", "question": "Q1", "expected_concepts": []}],
            "ios-docs",
            top_k=8,
            concurrency=1,
            testing_disable_rerank=True,
        )

    assert observed["rerank_client"] is None
    assert observed["coverage_gate_enabled"] is True
    assert observed["coverage_retry_enabled"] is True
    assert routes._rag_test_jobs[job_id]["results"][0]["status"] == "empty"


def test_rag_tests_v2_run_route_uses_collection_resolution_and_status_endpoints(
    monkeypatch,
) -> None:
    import api.http.rag_tests_routes as routes

    class _FakeThread:
        def __init__(self, target=None, args=None, kwargs=None, daemon=None):
            self.target = target
            self.args = args or ()
            self.kwargs = kwargs or {}
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(routes, "_select_tests_to_run", lambda _body: ([{"id": "t1", "name": "T1"}], None))
    monkeypatch.setattr(routes, "_resolve_collection_name", lambda _name: ("ios-docs", "qdrant.first_collection", None))
    monkeypatch.setattr(routes.threading, "Thread", _FakeThread)

    app = Flask(__name__)
    app.register_blueprint(routes.rag_tests_bp)
    client = app.test_client()

    response = client.post("/api/webui/rag-tests-v2/run", json={"top_k": 7, "concurrency": 2})
    assert response.status_code == 202
    body = response.get_json()
    assert body["collection_name"] == "ios-docs"
    assert body["collection_source"] == "qdrant.first_collection"
    assert body["mode"] == "retrieval_only"

    job_id = body["job_id"]
    status_response = client.get(f"/api/webui/rag-tests-v2/run/status/{job_id}")
    assert status_response.status_code == 200
    assert status_response.get_json()["mode"] == "retrieval_only"

    cancel_response = client.post(f"/api/webui/rag-tests-v2/run/cancel/{job_id}")
    assert cancel_response.status_code == 200
    assert routes._rag_test_jobs[job_id]["cancel_requested"] is True


def test_rag_tests_runs_delete_selected_ids(tmp_path) -> None:
    import api.http.rag_tests_routes as routes
    from infrastructure.database.rag_test_runs_repository import RagTestRunsRepository

    repo = RagTestRunsRepository(tmp_path / "webui.db")
    repo.add_run("run-1", "m1", "completed", 4, 4, 0, [])
    repo.add_run("run-2", "m1", "cancelled", 4, 0, 4, [])

    app = Flask(__name__)
    app.register_blueprint(routes.rag_tests_bp)

    routes.get_rag_test_runs_repository = lambda: repo
    client = app.test_client()

    response = client.delete(
        "/api/webui/rag-tests/runs",
        json={"run_ids": ["run-2"]},
    )

    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1
    assert repo.get_run("run-2") is None
    assert repo.get_run("run-1") is not None


def test_rag_tests_runs_delete_low_pass(tmp_path) -> None:
    import api.http.rag_tests_routes as routes
    from infrastructure.database.rag_test_runs_repository import RagTestRunsRepository

    repo = RagTestRunsRepository(tmp_path / "webui.db")
    repo.add_run("run-1", "m1", "completed", 8, 1, 7, [])
    repo.add_run("run-2", "m1", "completed", 8, 3, 5, [])

    app = Flask(__name__)
    app.register_blueprint(routes.rag_tests_bp)

    routes.get_rag_test_runs_repository = lambda: repo
    client = app.test_client()

    response = client.delete(
        "/api/webui/rag-tests/runs",
        json={"delete_low_pass": True, "max_pass_rate_pct": 25},
    )

    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1
    assert repo.get_run("run-1") is None
    assert repo.get_run("run-2") is not None


def test_rag_tests_run_export_includes_split_rag_metrics(tmp_path) -> None:
    import api.http.rag_tests_routes as routes
    from infrastructure.database.rag_test_runs_repository import RagTestRunsRepository

    repo = RagTestRunsRepository(tmp_path / "webui.db")
    repo.add_run(
        "run-1",
        "m1",
        "completed",
        1,
        0,
        1,
        [{
            "test_id": "t1",
            "test_name": "T1",
            "platform": "iOS",
            "framework": "Swift",
            "status": "FAIL",
            "response_time_ms": 12,
            "rag_used": True,
            "retrieval_used": True,
            "grounding_overlap": False,
            "strict_rag_ok": False,
            "strict_mode": True,
            "strict_quote_ok": False,
            "strict_quote_reason": "Missing RAG QUOTE block",
            "metrics_version": "v2_retrieval_grounding_split_2026_04_23",
            "evaluation_method_version": "v2_retrieval_grounding_split_2026_04_23",
            "confidence_label": "1/1 concepts found",
            "question": "Q",
        }],
    )

    app = Flask(__name__)
    app.register_blueprint(routes.rag_tests_bp)

    routes.get_rag_test_runs_repository = lambda: repo
    client = app.test_client()

    response = client.get("/api/webui/rag-tests/runs/run-1/export?format=csv")

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "retrieval_used" in text
    assert "grounding_overlap" in text
    assert "strict_rag_ok" in text
    assert "strict_mode" in text
    assert "strict_quote_ok" in text
    assert "strict_quote_reason" in text
    assert "metrics_version" in text


def test_rag_tests_runs_summary_includes_split_rag_metrics(tmp_path) -> None:
    from infrastructure.database.rag_test_runs_repository import RagTestRunsRepository

    repo = RagTestRunsRepository(tmp_path / "webui.db")
    repo.add_run(
        "run-1",
        "m1",
        "completed",
        2,
        1,
        1,
        [
            {"test_id": "t1", "status": "PASS", "framework": "Swift", "retrieval_used": True},
            {
                "test_id": "t2",
                "status": "FAIL",
                "framework": "Swift",
                "retrieval_used": True,
                "grounding_overlap": False,
                "strict_rag_ok": False,
            },
        ],
    )

    summary = repo.get_runs_summary(limit=10)

    assert summary["retrieval_used"] == 2
    assert summary["retrieval_rate_pct"] == 100.0
    assert summary["grounding_overlap"] == 0
    assert summary["strict_rag_total"] == 1
    assert summary["strict_rag_ok"] == 0
