from __future__ import annotations

import subprocess
import sys

from scripts import quality_gate


def test_quality_gate_profiles_are_registered() -> None:
    assert set(quality_gate.PROFILES) == {"minimal", "full", "release", "strict-lint"}


def test_minimal_gate_has_required_steps_and_timeouts() -> None:
    steps = quality_gate.iter_steps("minimal")
    names = [step.name for step in steps]

    assert names == [
        "ruff",
        "version-drift",
        "api-drift",
        "pytest-fast",
        "pytest-collect",
        "coreui-build",
        "coreui-knip",
        "coreui-lockfile",
    ]
    assert all(step.required for step in steps)
    assert all(step.timeout_seconds > 0 for step in steps)


def test_release_gate_keeps_startup_smoke_advisory() -> None:
    required = quality_gate.iter_steps("release")
    with_advisory = quality_gate.iter_steps("release", include_advisory=True)

    assert "startup-smoke-bat" not in [step.name for step in required]
    startup = next(step for step in with_advisory if step.name == "startup-smoke-bat")
    assert startup.required is False
    assert startup.timeout_seconds == 120


def test_quality_gate_help() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/quality_gate.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "quality gates" in result.stdout.lower()
