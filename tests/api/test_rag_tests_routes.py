from __future__ import annotations

import json

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
