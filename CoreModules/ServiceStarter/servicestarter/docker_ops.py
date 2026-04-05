"""Docker CLI helpers (subprocess)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests

from servicestarter.config import ServiceStarterConfig


def _resolved_docker_executable() -> str:
    env = (os.getenv("DOCKER_EXE") or "").strip()
    if env:
        return env
    found = shutil.which("docker")
    if found:
        return found
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = os.path.join(pf, "Docker", "Docker", "resources", "bin", "docker.exe")
        if os.path.isfile(candidate):
            return candidate
    return "docker"


def run_docker(args: list[str], *, timeout: float | None = 300.0) -> tuple[int, str, str]:
    exe = _resolved_docker_executable()
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        msg = (
            f"Docker CLI not found or not executable: {exe!r} "
            "(set DOCKER_EXE or add Docker to PATH)"
        )
        return 127, "", msg
    except PermissionError as e:
        return 126, "", f"Docker CLI permission denied: {exe!r}: {e}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, out, err


def docker_version_available() -> bool:
    code, _, _ = run_docker(["--version"], timeout=10.0)
    return code == 0


def docker_engine_info() -> tuple[bool, str]:
    """Return (engine_ready, detail) where detail is stderr/stdout on failure."""
    code, out, err = run_docker(["info"], timeout=15.0)
    if code == 0:
        return True, ""
    detail = (err or out or "").strip()
    return False, detail


def docker_engine_ready() -> bool:
    ok, _ = docker_engine_info()
    return ok


def container_name_matches_running(filter_name: str) -> bool:
    code, out, _ = run_docker(
        ["ps", "--filter", f"name={filter_name}", "--format", "{{.Names}}"],
        timeout=15.0,
    )
    if code != 0 or not out.strip():
        return False
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == filter_name or filter_name in line or line.endswith(filter_name):
            return True
    return False


def container_exists(name: str) -> bool:
    code, _, _ = run_docker(["inspect", name], timeout=15.0)
    return code == 0


def container_is_running(name: str) -> bool:
    """True if a container with this exact name exists and Docker reports State.Running (no substring ps filter)."""
    code, out, _ = run_docker(
        ["inspect", "-f", "{{.State.Running}}", name],
        timeout=15.0,
    )
    if code != 0:
        return False
    return (out or "").strip().lower() == "true"


def _wait_open_webui_container_running(
    name: str,
    *,
    timeout_sec: float = 45.0,
) -> tuple[bool, str | None]:
    """After docker run/start, confirm the container stays up or explain exit (e.g. wrong GPU image)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if container_is_running(name):
            return True, None
        code, st, _ = run_docker(
            ["inspect", "-f", "{{.State.Status}}", name],
            timeout=10.0,
        )
        if code == 0:
            status = (st or "").strip()
            if status in ("exited", "dead"):
                ecode, ec_out, _ = run_docker(
                    ["inspect", "-f", "{{.State.ExitCode}}", name],
                    timeout=10.0,
                )
                ec = (ec_out or "").strip() if ecode == 0 else "?"
                return False, (
                    f"container {name!r} exited (status={status}, exit={ec}). "
                    f"Check: docker logs {name}. "
                    "Without an NVIDIA GPU use OPEN_WEBUI_IMAGE=open-webui/open-webui:main "
                    f"then: docker rm -f {name}"
                )
        time.sleep(0.5)
    if container_is_running(name):
        return True, None
    return False, (
        f"container {name!r} not running after {int(timeout_sec)}s; "
        f"docker ps -a && docker logs {name}"
    )


def wait_for_docker_engine(
    cfg: ServiceStarterConfig,
    *,
    start_desktop_on_windows: bool = True,
) -> tuple[bool, str]:
    ready, last_detail = docker_engine_info()
    if ready:
        return True, "docker engine ready"

    if start_desktop_on_windows:
        if sys.platform == "win32":
            try:
                subprocess.Popen(
                    [cfg.docker_desktop_exe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                return False, f"failed to start Docker Desktop: {e}"

    deadline = time.monotonic() + cfg.docker_ready_timeout_sec
    last_err = "docker not ready"
    while time.monotonic() < deadline:
        ready, last_detail = docker_engine_info()
        if ready:
            return True, "docker engine became ready"
        time.sleep(cfg.docker_poll_interval_sec)
        last_err = "timeout waiting for docker info"
        if last_detail:
            last_err = f"{last_err}: {last_detail}"

    return False, last_err


def docker_pull(image: str, *, timeout: float = 600.0) -> tuple[bool, str]:
    code, out, err = run_docker(["pull", image], timeout=timeout)
    if code != 0:
        return False, err or out or f"docker pull failed ({code})"
    return True, out or "ok"


def docker_start_container(name: str) -> tuple[bool, str]:
    code, out, err = run_docker(["start", name], timeout=60.0)
    if code == 0:
        return True, (out or err or "ok").strip() or "ok"
    combined = f"{err}\n{out}".lower()
    if "already running" in combined or "is already running" in combined:
        return True, "already running"
    return False, (err or out or f"exit {code}").strip()


def _sync_restart_policy_unless_stopped(name: str) -> None:
    """Match `docker run --restart unless-stopped` for containers created without it (best-effort)."""
    run_docker(["update", "--restart", "unless-stopped", name], timeout=30.0)


def docker_stop_container(name: str) -> tuple[bool, str]:
    code, out, err = run_docker(["stop", name], timeout=120.0)
    ok = code == 0
    return ok, out or err or ("ok" if ok else f"exit {code}")


def ensure_qdrant_container(cfg: ServiceStarterConfig) -> tuple[bool, str]:
    name = cfg.qdrant_container_name
    if container_is_running(name):
        return True, "already running"

    if container_exists(name):
        ok_s, msg_s = docker_start_container(name)
        if ok_s:
            _sync_restart_policy_unless_stopped(name)
        return ok_s, msg_s

    ok_pull, msg_pull = docker_pull(cfg.qdrant_image)
    if not ok_pull:
        return False, msg_pull

    ports = [
        "-p",
        f"{cfg.qdrant_host_http_port}:6333",
        "-p",
        f"{cfg.qdrant_host_grpc_port}:6334",
    ]
    code, out, err = run_docker(
        [
            "run",
            "-d",
            *ports,
            "--name",
            name,
            "-v",
            "qdrant_storage:/qdrant/storage",
            "--restart",
            "unless-stopped",
            cfg.qdrant_image,
        ],
        timeout=120.0,
    )
    if code != 0:
        return False, err or out or f"docker run failed ({code})"
    return True, out or "created"


def ensure_open_webui_container(cfg: ServiceStarterConfig) -> tuple[bool, str]:
    name = cfg.open_webui_container_name
    if container_is_running(name):
        return True, "already running"

    if container_exists(name):
        ok_start, msg_start = docker_start_container(name)
        if not ok_start:
            return ok_start, msg_start
        up, wait_err = _wait_open_webui_container_running(name)
        if not up and wait_err:
            return False, wait_err
        _sync_restart_policy_unless_stopped(name)
        return True, msg_start

    ok_pull, msg_pull = docker_pull(cfg.open_webui_image)
    if not ok_pull:
        return False, msg_pull

    env_ollama = cfg.open_webui_ollama_url_for_container
    run_args: list[str] = [
        "run",
        "-d",
        "-p",
        f"{cfg.open_webui_host_port}:{cfg.open_webui_container_port}",
        "--name",
        name,
        "-e",
        f"OLLAMA_BASE_URL={env_ollama}",
        "--restart",
        "unless-stopped",
    ]
    if sys.platform != "win32":
        run_args.extend(["--add-host", "host.docker.internal:host-gateway"])
    run_args.append(cfg.open_webui_image)
    code, out, err = run_docker(run_args, timeout=180.0)
    if code != 0:
        return False, err or out or f"docker run failed ({code})"
    up, wait_err = _wait_open_webui_container_running(name)
    if not up and wait_err:
        return False, wait_err
    return True, out or "created"


def wait_for_http_json(
    url: str,
    *,
    path: str,
    ok_status: tuple[int, ...] = (200,),
    timeout_sec: float = 60.0,
    interval: float = 2.0,
) -> tuple[bool, str | None]:
    deadline = time.monotonic() + timeout_sec
    last_err: str | None = None
    base = url.rstrip("/")
    full = f"{base}{path}" if path.startswith("/") else f"{base}/{path}"
    while time.monotonic() < deadline:
        try:
            r = requests.get(full, timeout=3)
            if r.status_code in ok_status:
                return True, None
            last_err = f"http {r.status_code}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(interval)
    return False, last_err or "timeout"


def qdrant_port_from_url(url: str) -> int:
    parsed = urlparse(url) if "://" in url else urlparse(f"http://{url}")
    return int(parsed.port or 6333)


def open_webui_port_from_url(url: str) -> int:
    parsed = urlparse(url) if "://" in url else urlparse(f"http://{url}")
    return int(parsed.port or 3000)
