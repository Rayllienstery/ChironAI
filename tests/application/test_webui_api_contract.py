"""Contract guards between CoreUI API client and WebUI Flask routes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from flask import Blueprint, Flask

from api.http.rag_tests_routes import rag_tests_bp
from api.http.webui_routes import webui_bp
from api.http.webui_version_routes import register_version_routes
from core.contracts.webui_api import VERSION_RESPONSE_KEYS, WEBUI_URL_PREFIX
from core.openapi import build_openapi_spec, register_openapi_routes
from core.version import APP_NAME, APP_STAGE, VERSION

_ROOT = Path(__file__).resolve().parents[2]
_COREUI_API = _ROOT / "CoreModules" / "CoreUI" / "src" / "services" / "api.js"
_COREUI_HTTP = _ROOT / "CoreModules" / "CoreUI" / "src" / "services" / "http.js"


class _Logger:
    def error(self, *args: Any, **kwargs: Any) -> None:
        pass


def _frontend_api_base() -> str:
    for path in (_COREUI_HTTP, _COREUI_API):
        text = path.read_text(encoding="utf-8")
        match = re.search(
            r"(?:export const|const)\s+API_BASE\s*=\s*['\"]([^'\"]+)['\"]",
            text,
        )
        if match is not None:
            return match.group(1)
    raise AssertionError("CoreUI API_BASE constant was not found in http.js or api.js")


def test_frontend_api_base_matches_python_contract() -> None:
    assert _frontend_api_base() == WEBUI_URL_PREFIX


def test_webui_blueprints_use_contract_prefix() -> None:
    assert webui_bp.url_prefix == WEBUI_URL_PREFIX
    assert rag_tests_bp.url_prefix == WEBUI_URL_PREFIX


def test_version_route_matches_contract_shape() -> None:
    app = Flask(__name__)
    bp = Blueprint("version_contract", __name__, url_prefix=WEBUI_URL_PREFIX)
    register_version_routes(bp, error_log=_Logger())
    app.register_blueprint(bp)

    response = app.test_client().get(f"{WEBUI_URL_PREFIX}/version")
    data = response.get_json() or {}

    assert response.status_code == 200
    assert VERSION_RESPONSE_KEYS <= set(data)
    assert data["version"] == VERSION
    assert data["app_name"] == APP_NAME
    assert data["stage"] == APP_STAGE
    assert data["display_name"] == f"{APP_NAME} {APP_STAGE} {VERSION}"


def _openapi_contract_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(webui_bp)
    app.register_blueprint(rag_tests_bp)

    @app.route("/")
    def index() -> str:
        return ""

    @app.route("/health", methods=["GET"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.route("/v1/models", methods=["GET"])
    def v1_models() -> dict[str, object]:
        return {"object": "list", "data": []}

    @app.route("/v1/chat/completions", methods=["POST"])
    def v1_chat_completions() -> dict[str, object]:
        return {"choices": []}

    register_openapi_routes(app)
    return app


def test_openapi_json_route_exposes_expected_document() -> None:
    app = _openapi_contract_app()
    response = app.test_client().get(f"{WEBUI_URL_PREFIX}/openapi.json")
    spec = response.get_json() or {}

    assert response.status_code == 200
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == f"{APP_NAME} API"
    assert spec["info"]["version"] == VERSION
    assert "/api/webui/version" in spec["paths"]
    assert "/api/webui/rag/status" in spec["paths"]
    assert "/api/webui/extensions/installed" in spec["paths"]
    assert "/api/webui/docker/status" in spec["paths"]
    assert "/v1/models" in spec["paths"]
    assert "/v1/chat/completions" in spec["paths"]


def test_openapi_has_human_descriptions_and_structured_extension_tabs_schema() -> None:
    app = _openapi_contract_app()
    spec = build_openapi_spec(app)
    operation = spec["paths"]["/api/webui/extensions/tabs"]["get"]
    schema = spec["components"]["schemas"]["ExtensionTabsResponse"]

    assert operation["summary"] == "List extension tabs"
    assert "extension-owned CoreUI tab descriptors" in operation["description"]
    assert "tabs" in schema["properties"]
    assert schema["properties"]["tabs"]["items"]["$ref"] == "#/components/schemas/ExtensionTab"


def test_swagger_ui_route_returns_html() -> None:
    response = _openapi_contract_app().test_client().get(f"{WEBUI_URL_PREFIX}/swagger/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"SwaggerUIBundle" in response.data


def test_openapi_spec_covers_registered_flask_routes() -> None:
    app = _openapi_contract_app()
    spec = build_openapi_spec(app)
    spec_paths = set(spec["paths"])
    missing: list[str] = []

    for rule in app.url_map.iter_rules():
        endpoint = str(rule.endpoint or "")
        if endpoint in {"static", "openapi_json", "swagger_ui", "swagger_asset"}:
            continue
        path = re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule.rule)
        if path not in spec_paths:
            missing.append(path)

    assert not sorted(set(missing))
