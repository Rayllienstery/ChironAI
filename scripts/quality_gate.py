"""Run local and CI quality gates with explicit timeouts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COREUI_ROOT = REPO_ROOT / "CoreModules" / "CoreUI"


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    required: bool = True

    @property
    def kind(self) -> str:
        return "required" if self.required else "advisory"


def _npm_command(*args: str) -> tuple[str, ...]:
    executable = "npm.cmd" if os.name == "nt" else "npm"
    return (executable, *args)


def _python_command(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


MINIMAL_GATE: tuple[GateStep, ...] = (
    GateStep("ruff", ("ruff", "check", "."), REPO_ROOT, 120),
    GateStep("version-drift", _python_command("scripts/check_version_drift.py"), REPO_ROOT, 30),
    GateStep("api-drift", _python_command("scripts/check_api_drift.py", "--strict", "--strict-openapi"), REPO_ROOT, 60),
    GateStep("openapi-schema", _python_command("scripts/validate_openapi.py"), REPO_ROOT, 60),
    GateStep("pytest-fast", ("pytest", "-q", "-m", "fast", "--maxfail=1"), REPO_ROOT, 300),
    GateStep("pytest-collect", ("pytest", "--collect-only", "-q"), REPO_ROOT, 180),
    GateStep("coreui-build", _npm_command("run", "build"), COREUI_ROOT, 180),
    GateStep("coreui-bundle-budget", _npm_command("run", "bundle:budget"), COREUI_ROOT, 30),
    GateStep("coreui-knip", _npm_command("run", "knip"), COREUI_ROOT, 120),
    GateStep("coreui-lockfile", _npm_command("run", "check:lockfile"), COREUI_ROOT, 30),
)

FULL_GATE_EXTRA: tuple[GateStep, ...] = (
    GateStep("vulture", _python_command("-m", "vulture"), REPO_ROOT, 120),
    GateStep("pytest-full", ("pytest", "-q"), REPO_ROOT, 600),
    GateStep(
        "coverage-domain",
        (
            "pytest",
            "-q",
            "-m",
            "fast",
            "--cov=domain",
            "--cov=application",
            "--cov-report=xml",
            "--cov-fail-under=80",
        ),
        REPO_ROOT,
        300,
    ),
    GateStep(
        "oversized-files",
        _python_command("scripts/audit_oversized_files.py", "--mode", "check"),
        REPO_ROOT,
        60,
    ),
    GateStep(
        "silent-exceptions",
        _python_command("scripts/audit_silent_exceptions.py", "--mode", "check"),
        REPO_ROOT,
        60,
        required=False,
    ),
    GateStep(
        "import-linter",
        ("lint-imports",),
        REPO_ROOT,
        120,
        required=False,
    ),
    GateStep(
        "bandit",
        _python_command("-m", "bandit", "-r", "Core", "CoreModules", "-q"),
        REPO_ROOT,
        120,
        required=False,
    ),
    GateStep(
        "api-drift-check",
        _python_command("scripts/check_api_drift.py"),
        REPO_ROOT,
        60,
    ),
    GateStep("coreui-lint", _npm_command("run", "lint"), COREUI_ROOT, 120),
    GateStep("coreui-i18n-lint", _npm_command("run", "i18n-lint"), COREUI_ROOT, 60, required=False),
    GateStep("coreui-test", _npm_command("run", "test:run"), COREUI_ROOT, 180),
    GateStep("coreui-coverage", _npm_command("run", "test:coverage"), COREUI_ROOT, 180),
    GateStep("coreui-typecheck", _npm_command("run", "typecheck"), COREUI_ROOT, 120, required=True),
)

RELEASE_TYPING_GATE: tuple[GateStep, ...] = (
    GateStep("mypy", _python_command("-m", "mypy", "Core/domain", "Core/core"), REPO_ROOT, 180),
    GateStep("pyright", _python_command("-m", "pyright"), REPO_ROOT, 300),
)

FULL_GATE: tuple[GateStep, ...] = MINIMAL_GATE + FULL_GATE_EXTRA

STRICT_LINT_GATE: tuple[GateStep, ...] = (
    GateStep("ruff-strict", ("ruff", "check", ".", "--select", "E9,F,I,B,SIM"), REPO_ROOT, 180),
)

MUTATION_GATE: tuple[GateStep, ...] = (
    GateStep("mutation-baseline", ("mutmut", "run"), REPO_ROOT, 1800, required=False),
)

def _docker_available() -> bool:
    try:
        completed = subprocess.run(
            ("docker", "version"),
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _bash_available() -> bool:
    try:
        completed = subprocess.run(
            ("bash", "--version"),
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


RELEASE_GATE_EXTRA: tuple[GateStep, ...] = (
    GateStep(
        "dependency-audit",
        _python_command("scripts/run_dependency_audit.py"),
        REPO_ROOT,
        240,
    ),
    GateStep(
        "api-docs",
        _python_command("scripts/gen_api_docs.py", "--check"),
        REPO_ROOT,
        60,
        required=False,
    ),
    GateStep(
        "docker-build",
        ("docker", "build", "-t", "chironai:gate", "."),
        REPO_ROOT,
        600,
        required=_docker_available(),
    ),
    GateStep(
        "trivy-image",
        ("trivy", "image", "chironai:gate"),
        REPO_ROOT,
        300,
        required=False,
    ),
    GateStep(
        "startup-smoke-sh",
        ("bash", str(REPO_ROOT / "scripts" / "startup_smoke.sh")),
        REPO_ROOT,
        180,
        required=_bash_available() and os.name != "nt",
    ),
    GateStep(
        "startup-smoke-bat",
        (str(REPO_ROOT / "build_and_run.bat"),),
        REPO_ROOT,
        120,
        required=False,
    ),
)

RELEASE_GATE: tuple[GateStep, ...] = FULL_GATE + RELEASE_TYPING_GATE + RELEASE_GATE_EXTRA

PROFILES: dict[str, tuple[GateStep, ...]] = {
    "minimal": MINIMAL_GATE,
    "full": FULL_GATE,
    "strict-lint": STRICT_LINT_GATE,
    "release": RELEASE_GATE,
    "mutation": MUTATION_GATE,
}


def iter_steps(profile: str, *, include_advisory: bool = False) -> tuple[GateStep, ...]:
    steps = PROFILES[profile]
    if include_advisory:
        return steps
    return tuple(step for step in steps if step.required)


def format_command(step: GateStep) -> str:
    return subprocess.list2cmdline(step.command)


def run_step(step: GateStep) -> bool:
    print(f"\n==> {step.name} [{step.kind}, timeout={step.timeout_seconds}s]")
    print(f"cwd: {step.cwd}")
    print(f"$ {format_command(step)}")
    shell = os.name == "nt" and (
        step.command[0].lower().endswith(".bat") or step.command[0] == "bash"
    )
    command: str | tuple[str, ...] = format_command(step) if shell else step.command
    env = os.environ.copy()
    source_paths = [str(REPO_ROOT / "Core")]
    if env.get("PYTHONPATH"):
        source_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(source_paths)
    try:
        completed = subprocess.run(command, cwd=step.cwd, timeout=step.timeout_seconds, check=False, shell=shell, env=env)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT: {step.name} exceeded {step.timeout_seconds}s")
        return False
    except FileNotFoundError:
        print(f"SKIP: {step.name} — executable not found")
        return step.kind == "advisory"
    if completed.returncode == 0:
        print(f"PASS: {step.name}")
        return True
    print(f"FAIL: {step.name} exited with {completed.returncode}")
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ChironAI quality gates with stable timeouts.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="minimal", help="Gate profile to run.")
    parser.add_argument(
        "--include-advisory",
        action="store_true",
        help="Also run advisory steps such as Docker smoke and oversized-file audit.",
    )
    parser.add_argument("--list", action="store_true", help="Print selected steps without running them.")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --list.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    steps = iter_steps(args.profile, include_advisory=args.include_advisory)

    if args.list or args.dry_run:
        for step in steps:
            print(f"{step.name}\t{step.kind}\t{step.timeout_seconds}s\t{step.cwd}\t{format_command(step)}")
        return 0

    failed_required: list[str] = []
    failed_advisory: list[str] = []
    for step in steps:
        ok = run_step(step)
        if ok:
            continue
        if step.required:
            failed_required.append(step.name)
        else:
            failed_advisory.append(step.name)

    if failed_advisory:
        print("\nAdvisory failures: " + ", ".join(failed_advisory))
    if failed_required:
        print("\nRequired failures: " + ", ".join(failed_required))
        return 1
    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
