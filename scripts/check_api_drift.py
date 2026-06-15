"""Advisory drift check: Flask WebUI routes ↔ OpenAPI paths ↔ CoreUI api.js (Phase 1 / Track B)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBUI_PREFIX = "/api/webui"
V1_PREFIX = "/v1"

ROUTE_DECORATOR_RE = re.compile(
    r"""@(?:\w+\.)?route\(\s*['"]([^'"]+)['"]""",
)
API_JS_FETCH_RE = re.compile(
    r"""fetch\(\s*[`'"]\$\{API_BASE\}(/[^`'"]+)[`'"]""",
)
API_JS_TEMPLATE_RE = re.compile(
    r"""fetch\(\s*`\$\{API_BASE\}([^`]+)`""",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def collect_flask_webui_routes(webui_routes_dir: Path) -> set[str]:
    paths: set[str] = set()
    for py_file in sorted(webui_routes_dir.glob("webui_*.py")):
        text = _read_text(py_file)
        for match in ROUTE_DECORATOR_RE.finditer(text):
            sub = match.group(1).strip()
            if not sub.startswith("/"):
                sub = f"/{sub}"
            paths.add(f"{WEBUI_PREFIX}{sub}".rstrip("/") or WEBUI_PREFIX)
    return paths


def collect_v1_routes(rag_routes: Path) -> set[str]:
    paths: set[str] = set()
    text = _read_text(rag_routes)
    for match in ROUTE_DECORATOR_RE.finditer(text):
        sub = match.group(1).strip()
        if not sub.startswith("/"):
            sub = f"/{sub}"
        if sub.startswith("/v1") or sub.startswith("v1"):
            normalized = sub if sub.startswith("/") else f"/{sub}"
            paths.add(normalized.rstrip("/") or V1_PREFIX)
    return paths


def collect_openapi_paths(openapi_py: Path) -> set[str]:
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
                sub = match.group(1).split("?")[0].rstrip("/")
                if sub:
                    paths.add(f"{WEBUI_PREFIX}{sub}")
    return paths


def run_drift_check() -> tuple[list[str], list[str], list[str]]:
    webui_dir = REPO_ROOT / "api" / "http"
    rag_routes = REPO_ROOT / "api" / "http" / "rag_routes.py"
    openapi_py = REPO_ROOT / "core" / "openapi.py"
    api_js = REPO_ROOT / "CoreModules" / "CoreUI" / "src" / "services" / "api.js"
    services_dir = api_js.parent

    flask_paths = collect_flask_webui_routes(webui_dir)
    v1_paths = collect_v1_routes(rag_routes)
    openapi_paths = collect_openapi_paths(openapi_py)
    frontend_paths = collect_frontend_paths(services_dir)

    def norm(p: str) -> str:
        return re.sub(r"<[^>]+>", "{param}", p).rstrip("/")

    flask_norm = {norm(p) for p in flask_paths}
    openapi_norm = {norm(p) for p in openapi_paths}
    frontend_norm = {norm(p) for p in frontend_paths}

    frontend_not_in_flask = sorted(
        p for p in frontend_norm if p not in flask_norm and not p.endswith("{param}")
    )
    flask_not_in_openapi = sorted(p for p in flask_norm if p not in openapi_norm)
    openapi_not_in_flask = sorted(p for p in openapi_norm if p not in flask_norm and p.startswith(WEBUI_PREFIX))

    issues: list[str] = []
    if frontend_not_in_flask:
        issues.append("Frontend calls without obvious Flask route:")
        issues.extend(f"  - {p}" for p in frontend_not_in_flask[:30])
    if flask_not_in_openapi:
        issues.append("Flask WebUI routes missing from OpenAPI scan:")
        issues.extend(f"  - {p}" for p in flask_not_in_openapi[:30])
    if openapi_not_in_flask:
        issues.append("OpenAPI paths without Flask route scan match:")
        issues.extend(f"  - {p}" for p in openapi_not_in_flask[:30])
    if v1_paths:
        issues.append(f"V1 routes registered in rag_routes: {len(v1_paths)} (manual OpenAPI review)")

    return issues, frontend_not_in_flask, flask_not_in_openapi


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check API surface drift (advisory).")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when drift is detected.")
    args = parser.parse_args(argv)

    issues, frontend_miss, flask_miss = run_drift_check()
    if not issues:
        print("PASS: no obvious drift detected (heuristic scan).")
        return 0

    print("API drift check (advisory):")
    for line in issues:
        print(line)

    if args.strict and (frontend_miss or flask_miss):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
