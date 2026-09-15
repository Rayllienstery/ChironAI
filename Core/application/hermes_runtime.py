"""Host-owned Hermes Agent gateway lifecycle.

The hermes-agent extension never shells out. It calls this runtime through
``host_context.hermes_runtime``. The gateway stays a native host process.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from application.hermes_processes import (
    collect_managed_processes,
    empty_managed_processes,
    format_rss,
)

_log = logging.getLogger("chironai.hermes")

DEFAULT_API_PORT = 8642
DEFAULT_DASHBOARD_PORT = 9119
HEALTH_PATH = "/health"
INSTALL_URL = "https://hermes-agent.nousresearch.com/"
LOGIN_ITEM_NAME = "Hermes_Gateway.vbs"

_LIFECYCLE_BOUND = False


def _localappdata() -> Path:
    raw = (os.getenv("LOCALAPPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def _appdata() -> Path:
    raw = (os.getenv("APPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Roaming"


def hermes_home() -> Path:
    override = (os.getenv("HERMES_HOME") or "").strip()
    path = Path(override) if override else (_localappdata() / "hermes")
    try:
        return path.resolve()
    except OSError:
        return path


def login_item_path() -> Path:
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / LOGIN_ITEM_NAME


def default_health_url(port: int | None = None) -> str:
    return f"http://127.0.0.1:{int(port or DEFAULT_API_PORT)}{HEALTH_PATH}"


def default_dashboard_url(port: int | None = None) -> str:
    return f"http://127.0.0.1:{int(port or DEFAULT_DASHBOARD_PORT)}/"


def _config_summary(home: Path) -> dict[str, str]:
    """Read a few non-secret display fields from Hermes config.yaml."""

    path = home / "config.yaml"
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    section = ""
    default_model = ""
    image_provider = ""
    image_model = ""
    plugins: list[str] = []
    in_enabled = False
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0 and stripped.endswith(":") and not stripped.startswith("-"):
            section = stripped[:-1]
            in_enabled = False
            continue
        if section == "model" and stripped.startswith("default:"):
            default_model = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif section == "image_gen" and stripped.startswith("provider:"):
            image_provider = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif section == "image_gen" and stripped.startswith("model:"):
            image_model = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif section == "plugins" and stripped == "enabled:":
            in_enabled = True
        elif in_enabled and stripped.startswith("- "):
            plugins.append(stripped[2:].strip().strip('"').strip("'"))
        elif in_enabled and indent == 0:
            in_enabled = False
    image = " ".join(part for part in (image_provider, image_model) if part)
    return {
        "default_model": default_model,
        "image_gen": image,
        "plugins": ", ".join(plugins),
    }


def _read_api_port(home: Path) -> int:
    env_path = home / ".env"
    if not env_path.is_file():
        return DEFAULT_API_PORT
    try:
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() == "API_SERVER_PORT":
                return int(value.strip().strip('"').strip("'") or DEFAULT_API_PORT)
    except Exception:
        return DEFAULT_API_PORT
    return DEFAULT_API_PORT


def resolve_hermes_binary(
    *,
    which: Callable[[str], str | None] | None = None,
    home: Path | None = None,
) -> Path | None:
    finder = which or shutil.which
    for name in ("hermes.exe", "hermes"):
        found = finder(name)
        if found:
            path = Path(found)
            if path.is_file():
                return path
    base = home if home is not None else hermes_home()
    for candidate in (base / "bin" / "hermes.exe", base / "bin" / "hermes"):
        if candidate.is_file():
            return candidate
    return None


CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _windows_creation_flags(*, hide_only: bool = False, breakaway: bool = False) -> int:
    """Hidden-console flags for Windows Hermes child processes.

    Use ``CREATE_NO_WINDOW`` so the child owns a hidden console that
    descendants inherit. Do not combine it with ``DETACHED_PROCESS``:
    MSDN ignores ``CREATE_NO_WINDOW`` in that pair, and each nested
    ``python.exe`` then pops a visible Windows Terminal window.

    Long-lived gateway/dashboard spawns also set ``CREATE_BREAKAWAY_FROM_JOB``
    so a ChironAI console kill or job teardown does not SIGKILL Hermes
    mid-SSE (Open WebUI then reports TransferEncodingError).
    """
    if sys.platform != "win32":
        return 0
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW))
    if not hide_only:
        flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP))
        if breakaway:
            flags |= int(getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", CREATE_BREAKAWAY_FROM_JOB))
    return flags


class HermesRuntime:
    """Start, inspect, stop, and update the host Hermes gateway."""

    def __init__(
        self,
        *,
        run_cli: Callable[[list[str], float], dict[str, Any]] | None = None,
        spawn_gateway: Callable[[list[str]], dict[str, Any]] | None = None,
        health_probe: Callable[[str], dict[str, Any]] | None = None,
        which: Callable[[str], str | None] | None = None,
        login_path: Path | None = None,
        home: Path | None = None,
        list_processes: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._run_cli = run_cli
        self._spawn_gateway = spawn_gateway
        self._health_probe = health_probe
        self._which = which
        self._login_path = login_path
        self._home = home
        self._list_processes = list_processes

    def _home_dir(self) -> Path:
        return self._home if self._home is not None else hermes_home()

    def _binary(self) -> Path | None:
        return resolve_hermes_binary(which=self._which, home=self._home_dir())

    def _login_item(self) -> Path:
        return self._login_path if self._login_path is not None else login_item_path()

    def health_url(self) -> str:
        return default_health_url(_read_api_port(self._home_dir()))

    def dashboard_url(self) -> str:
        return default_dashboard_url()

    def _probe_health(self, url: str, *, timeout: float = 0.4) -> dict[str, Any]:
        if self._health_probe is not None:
            return dict(self._health_probe(url) or {})
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "ok": int(getattr(resp, "status", 200) or 200) < 400,
                    "http_status": int(getattr(resp, "status", 200) or 200),
                    "body": body,
                }
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            return {"ok": False, "http_status": None, "message": str(exc)}

    def _process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HERMES_HOME"] = str(self._home_dir())
        return env

    def _cli(self, args: list[str], *, timeout: float = 45.0) -> dict[str, Any]:
        if self._run_cli is not None:
            return dict(self._run_cli(args, timeout) or {})
        binary = self._binary()
        if binary is None:
            return {"ok": False, "code": 127, "stdout": "", "stderr": "hermes binary not found"}
        try:
            run_kwargs: dict[str, Any] = {
                "args": [str(binary), *args],
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": timeout,
                "check": False,
                "env": self._process_env(),
            }
            if sys.platform == "win32":
                run_kwargs["creationflags"] = _windows_creation_flags(hide_only=True)
            completed = subprocess.run(**run_kwargs)
        except subprocess.TimeoutExpired as exc:
            return {"ok": False, "code": 124, "stdout": str(exc.stdout or ""), "stderr": "timed out"}
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "ok": completed.returncode == 0,
            "code": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
        }

    def _spawn(self, args: list[str]) -> dict[str, Any]:
        if self._spawn_gateway is not None:
            return dict(self._spawn_gateway(args) or {})
        binary = self._binary()
        if binary is None:
            return {"ok": False, "message": "hermes binary not found"}
        try:
            kwargs: dict[str, Any] = {
                "args": [str(binary), *args],
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
                "env": self._process_env(),
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = _windows_creation_flags(breakaway=True)
            else:
                kwargs["start_new_session"] = True
            try:
                proc = subprocess.Popen(**kwargs)
            except OSError as exc:
                if sys.platform != "win32":
                    raise
                _log.warning("Hermes spawn breakaway failed (%s); retrying in the host job", exc)
                kwargs["creationflags"] = _windows_creation_flags()
                proc = subprocess.Popen(**kwargs)
            return {"ok": True, "pid": int(proc.pid)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def _parse_status_text(self, text: str) -> dict[str, Any]:
        running = False
        pid: int | None = None
        login = False
        for raw in (text or "").splitlines():
            line = raw.strip()
            lower = line.lower()
            if "gateway process running" in lower or "process running" in lower:
                running = True
            if "login item installed" in lower or ("startup" in lower and "installed" in lower):
                login = True
            if "pid" in lower:
                digits = "".join(ch if ch.isdigit() else " " for ch in line)
                parts = [part for part in digits.split() if part]
                if parts:
                    try:
                        pid = int(parts[-1])
                    except ValueError:
                        pid = pid
        return {"running": running, "pid": pid, "login_autostart": login}

    def inspect(self) -> dict[str, Any]:
        binary = self._binary()
        installed = binary is not None
        login = self._login_item().is_file()
        health_url = self.health_url()
        health = self._probe_health(health_url)
        running = bool(health.get("ok"))
        if not installed:
            tone = "warning"
            message = f"Hermes Agent is not installed. Install from {INSTALL_URL}"
        elif running:
            tone = "success"
            message = "running"
        else:
            tone = "neutral"
            message = "stopped"
        summary = _config_summary(self._home_dir()) if installed else {}
        if self._list_processes is not None:
            processes = list(self._list_processes() or [])
        else:
            processes = collect_managed_processes(api_port=_read_api_port(self._home_dir()))
        if not processes:
            processes = empty_managed_processes()
        rss_total = sum(int(item.get("rss_bytes") or 0) for item in processes)
        gateway_pid = next(
            (item.get("pid") for item in processes if item.get("id") == "gateway" and item.get("alive")),
            None,
        )
        return {
            "ok": installed,
            "installed": installed,
            "running": running,
            "tone": tone,
            "message": message,
            "pid": gateway_pid,
            "processes": processes,
            "rss_bytes": rss_total,
            "rss": format_rss(rss_total) if rss_total else "",
            "binary": str(binary) if binary is not None else "",
            "version": "",
            "home": str(self._home_dir()) if installed else "",
            "default_model": summary.get("default_model") or "",
            "image_gen": summary.get("image_gen") or "",
            "plugins": summary.get("plugins") or "",
            "health_url": health_url,
            "dashboard_url": self.dashboard_url(),
            "http_status": health.get("http_status"),
            "login_autostart": login,
            "install_url": INSTALL_URL,
            "updated_at": int(time.time()),
        }

    def _wait_until_url(self, url: str, *, timeout: float = 20.0) -> bool:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if bool(self._probe_health(url).get("ok")):
                return True
            time.sleep(0.4)
        return bool(self._probe_health(url).get("ok"))

    def _wait_until_running(self, *, timeout: float = 20.0) -> bool:
        return self._wait_until_url(self.health_url(), timeout=timeout)

    def _disable_login_autostart(self) -> dict[str, Any]:
        item = self._login_item()
        cli = self._cli(["gateway", "uninstall"], timeout=20.0)
        removed = False
        if item.is_file():
            try:
                item.unlink()
                removed = True
            except OSError as exc:
                return {"ok": False, "message": f"Could not remove login item: {exc}", "cli": cli}
        return {"ok": True, "removed": removed or bool(cli.get("ok")), "cli": cli}

    def ensure(self) -> dict[str, Any]:
        status = self.inspect()
        if not status.get("installed"):
            return {
                "ok": False,
                "message": status.get("message") or "Hermes Agent is not installed",
                "status": status,
            }
        autostart = self._disable_login_autostart()
        if status.get("running"):
            refreshed = self.inspect()
            return {
                "ok": True,
                "message": "Gateway already running",
                "status": refreshed,
                "autostart": autostart,
            }
        spawned = self._spawn(["gateway", "run"])
        if not spawned.get("ok"):
            return {
                "ok": False,
                "message": spawned.get("message") or "Failed to start Hermes gateway",
                "status": self.inspect(),
                "autostart": autostart,
            }
        ready = self._wait_until_running()
        refreshed = self.inspect()
        return {
            "ok": bool(ready or refreshed.get("running")),
            "message": "Gateway started" if ready or refreshed.get("running") else "Gateway start did not become healthy",
            "status": refreshed,
            "autostart": autostart,
            "spawn": spawned,
        }

    def stop(self) -> dict[str, Any]:
        status = self.inspect()
        if not status.get("installed"):
            return {"ok": True, "message": "Hermes Agent is not installed", "status": status}
        if not status.get("running"):
            return {"ok": True, "message": "Gateway already stopped", "status": status}
        cli = self._cli(["gateway", "stop"], timeout=20.0)
        time.sleep(0.3)
        refreshed = self.inspect()
        ok = not bool(refreshed.get("running"))
        return {
            "ok": ok or bool(cli.get("ok")),
            "message": "Gateway stopped" if ok else (cli.get("stderr") or cli.get("stdout") or "Stop requested"),
            "status": refreshed,
            "cli": cli,
        }

    def update(self) -> dict[str, Any]:
        status = self.inspect()
        if not status.get("installed"):
            return {
                "ok": False,
                "message": status.get("message") or "Hermes Agent is not installed",
                "status": status,
            }
        was_running = bool(status.get("running"))
        cli = self._cli(["update"], timeout=300.0)
        if was_running:
            self.stop()
            self.ensure()
        refreshed = self.inspect()
        return {
            "ok": bool(cli.get("ok")),
            "message": (cli.get("stdout") or cli.get("stderr") or "Update finished").strip().splitlines()[-1]
            if (cli.get("stdout") or cli.get("stderr"))
            else "Update finished",
            "status": refreshed,
            "cli": cli,
        }

    def ensure_dashboard(self, open_browser: bool = False) -> dict[str, Any]:
        url = self.dashboard_url()
        binary = self._binary()
        if binary is None:
            status = self.inspect()
            return {
                "ok": False,
                "message": status.get("message") or "Hermes Agent is not installed",
                "dashboard_url": url,
                "status": status,
            }
        if self._probe_health(url).get("ok"):
            if open_browser:
                self._open_os_browser(url)
            return {
                "ok": True,
                "message": url,
                "dashboard_url": url,
                "status": {"installed": True, "dashboard_url": url},
            }
        spawned = self._spawn(["dashboard", "--skip-build", "--no-open"])
        if not spawned.get("ok"):
            return {
                "ok": False,
                "message": spawned.get("message") or "Failed to start Hermes dashboard",
                "dashboard_url": url,
                "spawn": spawned,
            }
        ready = self._wait_until_url(url, timeout=45.0)
        if open_browser:
            self._open_os_browser(url)
        return {
            "ok": bool(ready),
            "message": url if ready else "Dashboard started but is not reachable yet",
            "dashboard_url": url,
            "spawn": spawned,
            "ready": bool(ready),
        }

    def _open_os_browser(self, url: str) -> None:
        target = str(url or "").strip()
        if not target:
            return
        try:
            if sys.platform == "win32":  # pragma: no cover
                os.startfile(target)  # nosec B606
            else:
                import webbrowser

                webbrowser.open(target)
        except OSError:
            _log.debug("Could not open Hermes dashboard in the OS browser", exc_info=True)


def bind_lifecycle_to_host() -> dict[str, Any]:
    """Start Hermes with this backend process.

    The gateway outlives ChironAI restarts: killing it on host exit cuts
    in-flight Open WebUI SSE streams. Stop it from the Hermes tab or the
    explicit WebUI server-stop route.
    """

    global _LIFECYCLE_BOUND
    _LIFECYCLE_BOUND = True
    runtime = HermesRuntime()
    result = runtime.ensure()
    ensure_dashboard = getattr(runtime, "ensure_dashboard", None)
    raw_dashboard = ensure_dashboard() if callable(ensure_dashboard) else None
    dashboard = raw_dashboard if isinstance(raw_dashboard, dict) else {}
    if result.get("ok"):
        _log.info("Hermes gateway bound to ChironAI host process")
    else:
        _log.warning("Hermes gateway was not started: %s", result.get("message"))
    if dashboard.get("ok"):
        _log.info("Hermes dashboard bound to ChironAI host process")
    elif dashboard:
        _log.warning("Hermes dashboard was not started: %s", dashboard.get("message"))
    return result


def stop_bound_gateway() -> dict[str, Any] | None:
    if not _LIFECYCLE_BOUND:
        return None
    try:
        return HermesRuntime().stop()
    except Exception:
        _log.debug("Hermes gateway stop during host shutdown failed", exc_info=True)
        return {"ok": False, "message": "Hermes stop failed"}


def is_lifecycle_bound() -> bool:
    return _LIFECYCLE_BOUND


def reset_lifecycle_for_tests() -> None:
    global _LIFECYCLE_BOUND
    _LIFECYCLE_BOUND = False


__all__ = [
    "DEFAULT_API_PORT",
    "INSTALL_URL",
    "HermesRuntime",
    "bind_lifecycle_to_host",
    "collect_managed_processes",
    "default_health_url",
    "hermes_home",
    "is_lifecycle_bound",
    "login_item_path",
    "reset_lifecycle_for_tests",
    "resolve_hermes_binary",
    "stop_bound_gateway",
]
