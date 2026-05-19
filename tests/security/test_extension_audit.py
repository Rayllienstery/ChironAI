from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from chironai_security import audit_extension, audit_extension_or_raise


def _write_extension(
    root: Path,
    *,
    provider_py: str,
    manifest_extra: dict[str, object] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    ext = root / "sample-ext"
    backend = ext / "backend"
    backend.mkdir(parents=True)
    (backend / "provider.py").write_text(provider_py, encoding="utf-8")
    for rel_path, text in (extra_files or {}).items():
        path = ext / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    manifest = {
        "id": "sample-ext",
        "version": "1.0.0",
        "api_version": "1",
        "type": "ui_extension",
        "title": "Sample",
        "icon": "icons/sample.svg",
        "backend": {"entrypoint": "backend.provider:create_provider"},
        "capabilities": {"tab_ui": True},
    }
    manifest.update(manifest_extra or {})
    (ext / "chironai-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ext


def _codes(report) -> set[str]:
    return {item.code for item in report.findings}


@pytest.mark.parametrize(
    ("provider_py", "expected_code"),
    [
        (
            """
import subprocess
def create_provider(host_context, manifest):
    subprocess.run(["cmd.exe", "/c", "whoami"], check=False)
    return object()
""",
            "shell_launcher",
        ),
        (
            """
import subprocess
def create_provider(host_context, manifest):
    subprocess.run("echo hi", shell=True)
    return object()
""",
            "subprocess_shell_true",
        ),
        (
            """
import os
def create_provider(host_context, manifest):
    os.system("whoami")
    return object()
""",
            "direct_shell_execution",
        ),
        (
            """
def create_provider(host_context, manifest):
    eval("1 + 1")
    return object()
""",
            "dynamic_code_execution",
        ),
        (
            """
def create_provider(host_context, manifest):
    command = "powershell -NoProfile -EncodedCommand SQBFAFgA"
    return object()
""",
            "powershell_encoded_command",
        ),
    ],
)
def test_extension_security_audit_blocks_dangerous_backend_patterns(
    tmp_path: Path,
    provider_py: str,
    expected_code: str,
) -> None:
    ext = _write_extension(tmp_path, provider_py=provider_py)

    report = audit_extension(ext, entrypoint="backend.provider:create_provider")

    assert report.blocked is True
    assert expected_code in _codes(report)
    with pytest.raises(ValueError, match="Extension security audit blocked"):
        audit_extension_or_raise(ext, entrypoint="backend.provider:create_provider")


def test_extension_security_audit_blocks_base64_decoded_shell_payload(tmp_path: Path) -> None:
    encoded = base64.b64encode("powershell -nop -c whoami".encode("utf-16-le")).decode("ascii")
    ext = _write_extension(
        tmp_path,
        provider_py=f"""
def create_provider(host_context, manifest):
    payload = "{encoded}"
    return object()
""",
    )

    report = audit_extension(ext, entrypoint="backend.provider:create_provider")

    assert report.blocked is True
    assert "encoded_command_payload" in _codes(report)


def test_extension_security_audit_warns_on_non_executable_base64(tmp_path: Path) -> None:
    encoded = base64.b64encode(("plain text " * 20).encode("utf-8")).decode("ascii")
    ext = _write_extension(
        tmp_path,
        provider_py=f"""
def create_provider(host_context, manifest):
    payload = "{encoded}"
    return object()
""",
    )

    report = audit_extension(ext, entrypoint="backend.provider:create_provider")

    assert report.blocked is False
    assert "encoded_content" in _codes(report)


def test_extension_security_audit_blocks_unsafe_manifest_url_and_path(tmp_path: Path) -> None:
    ext = _write_extension(
        tmp_path,
        provider_py="def create_provider(host_context, manifest):\n    return object()\n",
        manifest_extra={
            "icon": "../icons/sample.svg",
            "tab_ui": {"frame": {"url": "javascript:alert(1)"}},
        },
    )

    report = audit_extension(ext, entrypoint="backend.provider:create_provider")

    assert report.blocked is True
    assert {"manifest_unsafe_path", "manifest_unsafe_url"} <= _codes(report)


def test_bundled_extension_security_audit_allows_trusted_extensions() -> None:
    root = Path(__file__).resolve().parents[2]
    extension_dirs = sorted(path for path in (root / "extensions" / "bundled").iterdir() if path.is_dir())
    assert extension_dirs

    blocked: list[str] = []
    for extension_dir in extension_dirs:
        manifest = json.loads((extension_dir / "chironai-extension.json").read_text(encoding="utf-8"))
        entrypoint = str((manifest.get("backend") or {}).get("entrypoint") or "")
        report = audit_extension(extension_dir, entrypoint=entrypoint)
        if report.blocked:
            details = "; ".join(f"{item.code}:{item.file}" for item in report.blocking_findings)
            blocked.append(f"{extension_dir.name}: {details}")

    assert blocked == []
