from __future__ import annotations

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
