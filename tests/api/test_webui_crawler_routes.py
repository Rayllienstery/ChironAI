"""Characterization tests for split crawler route registration."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, Flask

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


def _crawler_rules() -> set[str]:
    import api.http.webui_crawler_routes as routes

    app = Flask(__name__)
    bp = Blueprint("webui_crawler_test", __name__, url_prefix="/api/webui")
    routes.register_crawler_routes(
        bp,
        error_log=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    app.register_blueprint(bp)
    return {rule.rule for rule in app.url_map.iter_rules()}


def test_register_crawler_routes_exposes_domain_endpoints() -> None:
    rules = _crawler_rules()
    assert "/api/webui/crawler/sources" in rules
    assert any("/crawler/indexer-tester/sources" in r for r in rules)
    assert any("/crawler/md-pipelines" in r for r in rules)
    assert any("/crawler/create-collection" in r for r in rules)
    assert any("/crawler/sources/<source_id>/crawl" in r for r in rules)


def test_clip_helpers_reexported_from_main_module() -> None:
    from api.http.webui_crawler_routes import (
        _clip_text_for_embedding,
        _is_embed_context_length_error,
        register_crawler_routes,
    )

    assert callable(_clip_text_for_embedding)
    assert callable(_is_embed_context_length_error)
    assert callable(register_crawler_routes)
