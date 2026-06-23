"""Tests for scripts/check_api_drift.py (Track B)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.fast
@pytest.mark.scripts
def test_check_api_drift_passes_strict() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_api_drift.py"), "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout or "no obvious drift" in result.stdout.lower()


@pytest.mark.fast
@pytest.mark.scripts
def test_openapi_v1_tag_is_llm_proxy() -> None:
    from api.http.rag_routes import create_app
    from core.openapi import build_openapi_spec

    app = create_app()
    spec = build_openapi_spec(app)
    paths = spec.get("paths") or {}
    v1_paths = [path for path in paths if path.startswith("/v1/")]
    assert v1_paths, "expected at least one /v1 path in OpenAPI"
    for path in v1_paths[:5]:
        for method, operation in (paths[path] or {}).items():
            if method.startswith("x-"):
                continue
            assert operation.get("tags") == ["Llm Proxy"], f"{path} {method} tags={operation.get('tags')}"
