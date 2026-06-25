from __future__ import annotations

import subprocess
import sys

from scripts import quality_gate


def test_quality_gate_profiles_are_registered() -> None:
    assert set(quality_gate.PROFILES) == {"minimal", "full", "mutation", "release", "strict-lint"}


def test_minimal_gate_has_required_steps_and_timeouts() -> None:
    steps = quality_gate.iter_steps("minimal")
    names = [step.name for step in steps]

    assert names == [
        "ruff",
        "bandit",
        "version-drift",
        "api-drift",
        "openapi-schema",
        "pytest-fast",
        "pytest-collect",
        "coreui-build",
        "coreui-bundle-budget",
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


def test_release_gate_requires_mypy_for_core_domain_typing() -> None:
    mypy = next(step for step in quality_gate.iter_steps("release") if step.name == "mypy")

    assert mypy.required is True
    assert mypy.timeout_seconds == 180
    assert mypy.command[-3:] == ("mypy", "Core/domain", "Core/core")


def test_release_gate_includes_advisory_trivy_image_scan() -> None:
    required = quality_gate.iter_steps("release")
    with_advisory = quality_gate.iter_steps("release", include_advisory=True)

    assert "trivy-image" not in [step.name for step in required]
    trivy = next(step for step in with_advisory if step.name == "trivy-image")
    assert trivy.required is False
    assert trivy.command == ("trivy", "image", "chironai:gate")


def test_full_gate_includes_advisory_coreui_i18n_lint() -> None:
    required = quality_gate.iter_steps("full")
    with_advisory = quality_gate.iter_steps("full", include_advisory=True)

    assert "coreui-i18n-lint" not in [step.name for step in required]
    step = next(item for item in with_advisory if item.name == "coreui-i18n-lint")
    assert step.required is False
    assert step.command[-2:] == ("run", "i18n-lint")


def test_full_gate_uses_coreui_test_run_script() -> None:
    step = next(item for item in quality_gate.iter_steps("full") if item.name == "coreui-test")

    assert step.required is True
    assert step.command[-2:] == ("run", "test:run")


def test_mutation_gate_is_advisory() -> None:
    assert quality_gate.iter_steps("mutation") == ()
    steps = quality_gate.iter_steps("mutation", include_advisory=True)

    assert len(steps) == 1
    assert steps[0].name == "mutation-baseline"
    assert steps[0].required is False
    assert steps[0].command == ("mutmut", "run")


def test_full_gate_requires_oversized_file_audit() -> None:
    oversized = next(step for step in quality_gate.iter_steps("full") if step.name == "oversized-files")

    assert oversized.required is True
    assert oversized.command[-3:] == ("scripts/audit_oversized_files.py", "--mode", "check")


def test_full_gate_requires_domain_application_coverage() -> None:
    coverage = next(step for step in quality_gate.iter_steps("full") if step.name == "coverage-domain")

    assert coverage.required is True
    assert "--cov=domain" in coverage.command
    assert "--cov=application" in coverage.command
    assert "--cov-fail-under=80" in coverage.command


def test_quality_gate_help() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/quality_gate.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "quality gates" in result.stdout.lower()
