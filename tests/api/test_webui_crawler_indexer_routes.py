"""HTTP tests for crawler indexer-tester routes."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Blueprint, Flask

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


@pytest.fixture()
def sources_tree(tmp_path: Path) -> Path:
    pages = tmp_path / "demo" / "pages"
    pages.mkdir(parents=True)
    (pages / "alpha.md").write_text("# Alpha\ncontent", encoding="utf-8")
    (pages / "beta.md").write_text("# Beta\nmore", encoding="utf-8")
    return tmp_path


def _client(sources_tree: Path, monkeypatch: pytest.MonkeyPatch):
    import api.http.webui_crawler_indexer_routes as routes

    monkeypatch.setattr(routes, "run_pipeline", lambda _name, md: ({"url": "x"}, f"processed:{md}"))
    monkeypatch.setattr(routes, "get_active_pipeline_name", lambda: "default")
    monkeypatch.setattr(routes, "list_collection_names", lambda: [])

    app = Flask(__name__)
    bp = Blueprint("webui_indexer_test", __name__, url_prefix="/api/webui")
    routes.register_crawler_indexer_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
        root=str(sources_tree),
        webui_backend=str(sources_tree),
        get_crawler_sources_dir=lambda: str(sources_tree),
        load_source_meta=lambda _sid: {"pages": {}},
        load_sources_config=lambda: [],
        save_sources_config=lambda _cfg: True,
    )
    app.register_blueprint(bp)
    return app.test_client()


def test_indexer_sources_lists_markdown_sources(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    data = client.get("/api/webui/crawler/indexer-tester/sources").get_json()
    assert {row["id"] for row in data["sources"]} == {"demo"}
    assert data["sources"][0]["page_count"] == 2


def test_indexer_sources_empty_when_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path / "missing", monkeypatch)
    data = client.get("/api/webui/crawler/indexer-tester/sources").get_json()
    assert data == {"sources": []}


def test_indexer_files_sorts_by_name_and_size(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    by_name = client.get("/api/webui/crawler/indexer-tester/sources/demo/files?sort=name&order=asc").get_json()
    assert [row["filename"] for row in by_name["files"]] == ["alpha.md", "beta.md"]

    by_size = client.get("/api/webui/crawler/indexer-tester/sources/demo/files?sort=size&order=desc").get_json()
    assert by_size["files"][0]["filename"] in {"alpha.md", "beta.md"}
    assert by_size["total"] == 2


def test_indexer_files_unknown_source_returns_404(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    response = client.get("/api/webui/crawler/indexer-tester/sources/missing/files")
    assert response.status_code == 404


def test_indexer_file_detail_returns_processed_markdown(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    response = client.get("/api/webui/crawler/indexer-tester/sources/demo/files/alpha.md")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filename"] == "alpha.md"
    assert payload["source_md"].startswith("# Alpha")
    assert payload["processed_md"].startswith("processed:")


def test_indexer_file_detail_rejects_path_traversal(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    response = client.get("/api/webui/crawler/indexer-tester/sources/demo/files/../alpha.md")
    assert response.status_code in {400, 404}


def test_indexer_evaluate_requires_content(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    response = client.post("/api/webui/crawler/indexer-tester/evaluate", json={})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]["message"].lower()


def test_indexer_evaluate_returns_reply_when_llm_available(
    sources_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.http.webui_crawler_indexer_routes as routes

    client = _client(sources_tree, monkeypatch)
    chat_client = MagicMock()
    chat_client.chat.return_value = "looks good"
    deps = SimpleNamespace(chat_client=chat_client)
    params = SimpleNamespace(model_name="test-model")
    monkeypatch.setattr(
        routes,
        "get_rag_answer_params",
        lambda **_kwargs: (params, deps),
    )

    response = client.post(
        "/api/webui/crawler/indexer-tester/evaluate",
        json={"source_md": "# A", "processed_md": "# B"},
    )
    assert response.status_code == 200
    assert response.get_json()["reply"] == "looks good"


def test_indexer_evaluate_batch_validates_input(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    missing_source = client.post("/api/webui/crawler/indexer-tester/evaluate-batch", json={"count": 2})
    assert missing_source.status_code == 400

    bad_count = client.post(
        "/api/webui/crawler/indexer-tester/evaluate-batch",
        json={"source_id": "demo", "count": 0},
    )
    assert bad_count.status_code == 400


def test_indexer_evaluate_batch_status_unknown_job(sources_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(sources_tree, monkeypatch)
    response = client.get("/api/webui/crawler/indexer-tester/evaluate-batch/status/not-a-job")
    assert response.status_code == 404
