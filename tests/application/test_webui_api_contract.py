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
from core.version import APP_NAME, APP_STAGE, VERSION


_ROOT = Path(__file__).resolve().parents[2]
_COREUI_API = _ROOT / "CoreModules" / "CoreUI" / "src" / "services" / "api.js"


class _Logger:
    def error(self, *args: Any, **kwargs: Any) -> None:
        pass


def _frontend_api_base() -> str:
    text = _COREUI_API.read_text(encoding="utf-8")
    match = re.search(r"const\s+API_BASE\s*=\s*['\"]([^'\"]+)['\"]", text)
    assert match is not None, "CoreUI API_BASE constant was not found"
    return match.group(1)


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
