"""Download and run Windows installers (Docker Desktop, Ollama)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import requests


def download_file(url: str, dest: Path, *, timeout: float = 600.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def install_docker_desktop(installer_path: Path) -> tuple[bool, str]:
    """
    Run Docker Desktop unattended install.
    See Docker docs: installer supports `install --quiet`.
    """
    try:
        proc = subprocess.run(
            [
                str(installer_path),
                "install",
                "--quiet",
                "--accept-license",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        err = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode != 0:
            return False, err or f"installer exited {proc.returncode}"
        return True, "docker desktop installed"
    except subprocess.TimeoutExpired:
        return False, "docker desktop installer timeout"
    except OSError as e:
        return False, str(e)


def install_ollama(installer_path: Path) -> tuple[bool, str]:
    """Inno Setup style silent flags for Ollama Windows installer."""
    try:
        proc = subprocess.run(
            [
                str(installer_path),
                "/SP-",
                "/VERYSILENT",
                "/NORESTART",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        err = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode != 0:
            return False, err or f"OllamaSetup exited {proc.returncode}"
        return True, "ollama installed"
    except subprocess.TimeoutExpired:
        return False, "ollama installer timeout"
    except OSError as e:
        return False, str(e)


def ensure_docker_desktop_installed(
    installer_url: str,
    *,
    cache_dir: Path | None = None,
) -> tuple[bool, str]:
    """Download Docker Desktop installer if needed and run it."""
    if cache_dir is None:
        cache_dir = Path(tempfile.gettempdir()) / "servicestarter_installers"
    dest = cache_dir / "DockerDesktopInstaller.exe"
    try:
        download_file(installer_url, dest)
    except Exception as e:
        return False, f"download docker: {e}"
    return install_docker_desktop(dest)


def ensure_ollama_installed(
    installer_url: str,
    *,
    cache_dir: Path | None = None,
) -> tuple[bool, str]:
    if cache_dir is None:
        cache_dir = Path(tempfile.gettempdir()) / "servicestarter_installers"
    dest = cache_dir / "OllamaSetup.exe"
    try:
        download_file(installer_url, dest)
    except Exception as e:
        return False, f"download ollama: {e}"
    return install_ollama(dest)
