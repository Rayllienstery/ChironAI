from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, Flask

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


def _client():
    import api.http.webui_help_routes as routes

    app = Flask(__name__)
    bp = Blueprint("webui_help_test", __name__, url_prefix="/api/webui")
    routes.register_help_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    app.register_blueprint(bp)
    return app.test_client()


def test_help_list_returns_index_entries() -> None:
    data = _client().get("/api/webui/help").get_json()
    assert isinstance(data.get("articles"), list)
    assert len(data["articles"]) >= 7
    assert data["articles"][0]["slug"]


def test_help_get_article_by_slug() -> None:
    response = _client().get("/api/webui/help/getting-started")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["slug"] == "getting-started"
    assert "Welcome to ChironAI" in payload["content"]


def test_help_get_unknown_slug_returns_404() -> None:
    response = _client().get("/api/webui/help/not-a-real-topic")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"].lower()


def test_help_search_requires_query_for_results() -> None:
    empty = _client().get("/api/webui/help/search").get_json()
    assert empty["results"] == []

    data = _client().get("/api/webui/help/search?q=builds").get_json()
    assert data["query"] == "builds"
    assert any(row.get("slug") == "builds" for row in data["results"])
