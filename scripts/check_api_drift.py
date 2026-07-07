"""Advisory drift check: Flask WebUI routes ↔ OpenAPI paths ↔ CoreUI api.js (Phase 1 / Track B)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = REPO_ROOT / "Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))
WEBUI_PREFIX = "/api/webui"
V1_PREFIX = "/v1"

ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:\w+\.)?(?:route|get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""",
)
API_JS_FETCH_RE = re.compile(
    r"""fetch\(\s*[`'"]\$\{API_BASE\}(/[^`'"]+)[`'"]""",
)
API_JS_TEMPLATE_RE = re.compile(
    r"""fetch\(\s*`\$\{API_BASE\}([^`]+)`""",
)
# Collapse `${encodeURIComponent(x)}` and other template interpolations to a route param token.
_TEMPLATE_EXPR_RE = re.compile(r"\$\{[^}]+\}")
_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")
_FLASK_PARAM_RE = re.compile(r"<(?:[^:>]+:)?[^>]+>")


def _normalize_route_path(path: str) -> str:
    normalized = _FLASK_PARAM_RE.sub("{param}", path.strip())
    normalized = _PATH_PARAM_RE.sub("{param}", normalized)
    return normalized.rstrip("/") or "/"


def _normalize_frontend_subpath(sub: str) -> str:
    """Turn a fetch template fragment into a comparable static route path."""
    sub = sub.split("?")[0].rstrip("/")
    sub = _TEMPLATE_EXPR_RE.sub("{param}", sub)
    # Truncate glued template tails (e.g. ``${query ? `?${query}` : ''}``).
    if "$" in sub:
        sub = sub.split("$", 1)[0]
    sub = sub.strip("`'\"").rstrip("/")
    return sub


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def collect_flask_webui_routes(webui_routes_dir: Path) -> set[str]:
    paths: set[str] = set()
    py_files = sorted(webui_routes_dir.glob("webui_*.py"))
    rag_tests = webui_routes_dir / "rag_tests_routes.py"
    if rag_tests.is_file():
        py_files.append(rag_tests)
    for py_file in py_files:
        text = _read_text(py_file)
        for match in ROUTE_DECORATOR_RE.finditer(text):
            sub = match.group(1).strip()
            if not sub.startswith("/"):
                sub = f"/{sub}"
            paths.add(f"{WEBUI_PREFIX}{sub}".rstrip("/") or WEBUI_PREFIX)
    return paths


def collect_v1_routes(v1_blueprint_py: Path) -> set[str]:
    paths: set[str] = set()
    text = _read_text(v1_blueprint_py)
    for match in ROUTE_DECORATOR_RE.finditer(text):
        sub = match.group(1).strip()
        if not sub.startswith("/"):
            sub = f"/{sub}"
        if sub.startswith("/v1") or sub.startswith("v1"):
            normalized = sub if sub.startswith("/") else f"/{sub}"
            paths.add(normalized.rstrip("/") or V1_PREFIX)
    return paths


def collect_openapi_paths_from_spec() -> set[str]:
    """Build OpenAPI from the live Flask route map (source of truth)."""
    try:
        from core.bootstrap.import_paths import ensure_webui_composition_paths

        ensure_webui_composition_paths(REPO_ROOT)
        from api.http.rag_routes import create_app
        from core.openapi import build_openapi_spec

        app = create_app(bootstrap_extensions=False)
        spec = build_openapi_spec(app)
        return {str(path).rstrip("/") or "/" for path in spec.get("paths", {})}
    except Exception:
        return set()


def collect_openapi_paths_heuristic(openapi_py: Path) -> set[str]:
    text = _read_text(openapi_py)
    paths: set[str] = set()
    for match in re.finditer(r"""['"](/api/webui/[^'"]+)['"]""", text):
        paths.add(match.group(1).rstrip("/"))
    for match in re.finditer(r"""['"](/v1/[^'"]+)['"]""", text):
        paths.add(match.group(1).rstrip("/"))
    return paths


def collect_frontend_paths(services_dir: Path) -> set[str]:
    paths: set[str] = set()
    js_files = [services_dir / "api.js"]
    js_files.extend(sorted(services_dir.glob("*.js")))
    seen: set[Path] = set()
    for js_file in js_files:
        if js_file in seen or not js_file.is_file():
            continue
        seen.add(js_file)
        text = _read_text(js_file)
        for pattern in (API_JS_FETCH_RE, API_JS_TEMPLATE_RE):
            for match in pattern.finditer(text):
                sub = _normalize_frontend_subpath(match.group(1))
                if sub:
                    paths.add(f"{WEBUI_PREFIX}{sub}")
    return paths


def run_drift_check() -> tuple[list[str], list[str], list[str], int]:
    webui_dir = REPO_ROOT / "Core" / "api" / "http"
    v1_blueprint_py = REPO_ROOT / "CoreModules" / "LlmProxy" / "llm_proxy" / "v1_blueprint.py"
    openapi_py = REPO_ROOT / "Core" / "core" / "openapi.py"
    api_js = REPO_ROOT / "CoreModules" / "CoreUI" / "src" / "services" / "api.js"
    services_dir = api_js.parent

    flask_paths = collect_flask_webui_routes(webui_dir)
    v1_paths = collect_v1_routes(v1_blueprint_py)
    flask_paths |= v1_paths
    openapi_paths = collect_openapi_paths_from_spec()
    if not openapi_paths:
        openapi_paths = collect_openapi_paths_heuristic(openapi_py)
    frontend_paths = collect_frontend_paths(services_dir)

    flask_norm = {_normalize_route_path(p) for p in flask_paths}
    openapi_norm = {_normalize_route_path(p) for p in openapi_paths}
    frontend_norm = {_normalize_route_path(p) for p in frontend_paths}

    frontend_not_in_flask = sorted(
        p for p in frontend_norm if p not in flask_norm and not p.endswith("{param}")
    )
    flask_not_in_openapi = sorted(p for p in flask_norm if p not in openapi_norm)
    openapi_not_in_flask = sorted(
        p for p in openapi_norm if p not in flask_norm and p.startswith(WEBUI_PREFIX)
    )

    issues: list[str] = []
    if frontend_not_in_flask:
        issues.append("Frontend calls without obvious Flask route:")
        issues.extend(f"  - {p}" for p in frontend_not_in_flask[:30])
    if flask_not_in_openapi:
        issues.append("Flask routes missing from generated OpenAPI:")
        issues.extend(f"  - {p}" for p in flask_not_in_openapi[:30])
    if openapi_not_in_flask:
        issues.append("OpenAPI paths without Flask route scan match:")
        issues.extend(f"  - {p}" for p in openapi_not_in_flask[:30])

    return issues, frontend_not_in_flask, flask_not_in_openapi, len(v1_paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check API surface drift (advisory).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when frontend calls lack a Flask route (primary contract).",
    )
    parser.add_argument(
        "--strict-openapi",
        action="store_true",
        help="Also exit 1 when Flask routes are missing from generated OpenAPI.",
    )
    args = parser.parse_args(argv)

    issues, frontend_miss, flask_miss, v1_count = run_drift_check()
    if not issues:
        print("PASS: no obvious drift detected (heuristic scan).")
        if v1_count:
            print(f"V1 routes in v1_blueprint: {v1_count}")
        return 0

    print("API drift check (advisory):")
    for line in issues:
        print(line)
    if v1_count:
        print(f"V1 routes in v1_blueprint: {v1_count}")

    if args.strict and frontend_miss:
        return 1
    if args.strict_openapi and flask_miss:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
