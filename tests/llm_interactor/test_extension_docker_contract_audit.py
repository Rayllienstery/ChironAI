from __future__ import annotations

from pathlib import Path

from llm_interactor.discovery import load_manifest_from_dir, validate_extension_backend_docker_policy


def test_bundled_extension_backends_do_not_shell_out_to_docker() -> None:
    root = Path(__file__).resolve().parents[2]
    extension_dirs = sorted(path for path in (root / "extensions" / "bundled").iterdir() if path.is_dir())
    assert extension_dirs

    violations: list[str] = []
    for extension_dir in extension_dirs:
        manifest = load_manifest_from_dir(extension_dir)
        assert manifest.backend is not None
        try:
            validate_extension_backend_docker_policy(extension_dir, manifest.backend.entrypoint)
        except ValueError as e:
            violations.append(f"{extension_dir.relative_to(root)}: {e}")

    assert violations == []
