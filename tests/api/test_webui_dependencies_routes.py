from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, Flask

_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MANAGER = _ROOT / "CoreModules" / "ErrorManager"
if str(_ERROR_MANAGER) not in sys.path:
    sys.path.insert(0, str(_ERROR_MANAGER))


def _write_dependency_fixture(root: Path) -> None:
    (root / "CoreModules" / "CoreUI").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        """
[project]
dependencies = [
  "flask",
  "requests>=2",
]

[project.optional-dependencies]
dev = [
  "pytest>=7",
]
""".strip(),
        encoding="utf-8",
    )
    (root / "requirements-dev.txt").write_text(
        """
# local editable installs are workspace packages, not third-party rows
-e .[dev]
httpx>=0.27
""".strip(),
        encoding="utf-8",
    )
    (root / "CoreModules" / "CoreUI" / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"react": "^18.2.0"},
                "devDependencies": {"vite": "^5.0.8"},
            }
        ),
        encoding="utf-8",
    )
    (root / "CoreModules" / "CoreUI" / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"dependencies": {"react": "^18.2.0"}, "devDependencies": {"vite": "^5.0.8"}},
                    "node_modules/react": {"version": "18.2.0"},
                    "node_modules/vite": {"version": "5.0.8"},
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        """
services:
  qdrant:
    image: qdrant/qdrant:latest
""".strip(),
        encoding="utf-8",
    )


def test_build_dependency_inventory_reads_python_npm_and_docker(monkeypatch, tmp_path):
    import api.http.webui_dependencies_routes as routes

    _write_dependency_fixture(tmp_path)
    monkeypatch.setattr(routes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(routes, "COREUI_ROOT", tmp_path / "CoreModules" / "CoreUI")
    monkeypatch.setattr(routes, "_python_installed_version", lambda name: "3.1.0" if name == "flask" else None)

    inventory = routes.build_dependency_inventory()
    deps = {item["id"]: item for item in inventory["dependencies"]}

    assert inventory["counts"]["python"] == 4
    assert inventory["counts"]["npm"] == 2
    assert inventory["counts"]["docker"] == 1
    assert deps["python:flask"]["installed_version"] == "3.1.0"
    assert deps["python:httpx"]["requested"] == "httpx>=0.27"
    assert deps["npm:react"]["installed_version"] == "18.2.0"
    assert deps["docker:qdrant/qdrant"]["status"] == "declared"


def test_dependencies_route_returns_inventory(monkeypatch, tmp_path):
    import api.http.webui_dependencies_routes as routes

    _write_dependency_fixture(tmp_path)
    monkeypatch.setattr(routes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(routes, "COREUI_ROOT", tmp_path / "CoreModules" / "CoreUI")
    monkeypatch.setattr(routes, "_python_installed_version", lambda name: None)

    app = Flask(__name__)
    bp = Blueprint("webui_dependencies_test", __name__, url_prefix="/api/webui")
    routes.register_dependencies_routes(bp, error_log=SimpleNamespace(error=lambda *args, **kwargs: None))
    app.register_blueprint(bp)

    response = app.test_client().get("/api/webui/dependencies")

    assert response.status_code == 200
    data = response.get_json()
    assert data["counts"]["total"] == 7
    assert any(item["name"] == "react" for item in data["dependencies"])
