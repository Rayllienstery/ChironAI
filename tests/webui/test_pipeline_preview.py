"""GET /api/webui/pipeline-preview returns proxy/RAG flags for the Web UI diagram."""

import pytest


@pytest.fixture(autouse=True)
def _disable_background_extension_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    from llm_interactor import ExtensionManager

    monkeypatch.setattr(ExtensionManager, "start_background_bootstrap", lambda self: None)


def test_pipeline_preview_returns_expected_keys() -> None:
    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/api/webui/pipeline-preview")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    assert "error" not in data
    assert data.get("rag_collection_configured") in (True, False)
    assert data.get("hybrid_sparse_enabled") in (True, False)
    assert data.get("rerank_for_rag") in (True, False)
    assert data.get("fetch_web_knowledge") in (True, False)
    assert data.get("web_interaction_enabled") in (True, False)
    env = data.get("env")
    assert isinstance(env, dict)
    assert "web_interaction_globally_enabled" in env
    assert "ddg_news" in env
    assert "fetch_page" in env
    assert "wikipedia" in env
    env_raw = data.get("env_raw")
    assert isinstance(env_raw, dict)
    assert "ddg_news" in env_raw
    assert "fetch_page" in env_raw
    assert "wikipedia" in env_raw
    pipeline_definition = data.get("pipeline_definition")
    assert isinstance(pipeline_definition, dict)
    rag_def = pipeline_definition.get("rag")
    assert isinstance(rag_def, dict)
    assert isinstance(rag_def.get("steps"), list)
    assert len(rag_def["steps"]) >= 1
    proxy_def = pipeline_definition.get("proxy")
    assert isinstance(proxy_def, dict)
    assert isinstance(proxy_def.get("steps"), list)
    assert len(proxy_def["steps"]) >= 1
    assert isinstance(data.get("proxy_last_executed_steps"), list)


def test_pipeline_definition_endpoint_returns_steps() -> None:
    from api.http.rag_routes import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/api/webui/pipeline-definition")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    assert "error" not in data
    pd = data.get("pipeline_definition")
    assert isinstance(pd, dict)
    rag_def = pd.get("rag")
    assert isinstance(rag_def, dict)
    assert isinstance(rag_def.get("steps"), list)
    assert len(rag_def["steps"]) >= 1
    proxy_def = pd.get("proxy")
    assert isinstance(proxy_def, dict)
    assert isinstance(proxy_def.get("steps"), list)
    assert len(proxy_def["steps"]) >= 1
    assert isinstance(data.get("proxy_last_executed_steps"), list)
