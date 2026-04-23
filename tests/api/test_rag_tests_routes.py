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

    def _validate_result(_test, _content, _metadata):
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
        )

    assert captured.get("model") == "llama3"
    assert captured.get("collection_name") == "ios-docs"
    assert captured.get("prompt_name") == "system_senior_ios_assistant_v1"
    assert captured.get("top_k") == 8.0
    assert captured.get("testing_disable_rerank") is True


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
