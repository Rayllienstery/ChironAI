from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script_help(script_name: str) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / "scripts" / script_name
    return subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sync_bundled_extensions_help() -> None:
    result = _run_script_help("sync_bundled_extensions.py")
    assert result.returncode == 0, result.stderr
    assert "bundled bootstrap extension" in result.stdout.lower()


def test_audit_apple_ingest_filter_help() -> None:
    result = _run_script_help("audit_apple_ingest_filter.py")
    assert result.returncode == 0, result.stderr
    assert "apple" in result.stdout.lower()


def test_quality_gate_help() -> None:
    result = _run_script_help("quality_gate.py")
    assert result.returncode == 0, result.stderr
    assert "quality gates" in result.stdout.lower()


def test_check_version_drift_help() -> None:
    result = _run_script_help("check_version_drift.py")
    assert result.returncode == 0, result.stderr
    assert "versions match" in result.stdout.lower()


def test_sync_version_help() -> None:
    result = _run_script_help("sync_version.py")
    assert result.returncode == 0, result.stderr
    assert "synchronize" in result.stdout.lower()


def test_validate_openapi_help() -> None:
    result = _run_script_help("validate_openapi.py")
    assert result.returncode == 0, result.stderr
    assert "openapi 3.1" in result.stdout.lower()


def test_print_quality_gate_pythonpath_includes_core_and_rag_service() -> None:
    script = REPO_ROOT / "scripts" / "print_quality_gate_pythonpath.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    paths = result.stdout.strip().split(";") if os.name == "nt" else result.stdout.strip().split(":")
    assert any(path.endswith("Core") or path.endswith("Core\\") for path in paths)
    assert any("RagService" in path for path in paths)
