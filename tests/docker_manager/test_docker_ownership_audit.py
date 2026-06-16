from __future__ import annotations

from pathlib import Path


def test_docker_mechanics_are_owned_by_docker_manager() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed_root = root / "CoreModules" / "DockerManager"
    scanned_roots = [
        root / "Core" / "api",
        root / "CoreModules",
        root / "extensions",
        root / "Core" / "infrastructure",
        root / "Core" / "modules",
        root / "WebUI",
    ]
    banned = [
        "DOCKER_EXE",
        "_resolved_docker_executable",
        "run_docker",
        'shutil.which("docker")',
        "shutil.which('docker')",
    ]
    violations: list[str] = []

    for scan_root in scanned_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.py"):
            if allowed_root in path.parents:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in banned:
                if needle in text:
                    violations.append(f"{path.relative_to(root)} contains {needle!r}")

    assert violations == []
