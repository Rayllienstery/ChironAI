"""
Light integration tests for HTTP endpoints (Flask test client).
"""

from __future__ import annotations

import pytest


def test_health_endpoint() -> None:
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app
    app = create_app()
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("status") == "ok"


def test_models_endpoint() -> None:
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from api.http.rag_routes import create_app
    app = create_app()
    client = app.test_client()
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.get_json()
    assert "data" in data
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "rag-ollama"
