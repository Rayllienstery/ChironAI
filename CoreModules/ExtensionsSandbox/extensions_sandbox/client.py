"""Host-side client for extension worker processes."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import weakref
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from extensions_sandbox.serialization import to_jsonable


class ExtensionWorkerError(RuntimeError):
    """Raised when a sandbox worker fails or returns an error."""


class ExtensionWorkerTimeout(TimeoutError):
    """Raised when a sandbox worker call times out."""


_HOST_CALL_TIMEOUTS: dict[tuple[str, str], float] = {
    ("docker_runtime", "inspect_container"): 1.5,
}

_log = logging.getLogger("chironai.extensions")


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()


class ExtensionWorkerClient:
    """Line-delimited JSON RPC client for one extension worker."""

    MAX_AUTO_RESTARTS = 2

    def __init__(
        self,
        *,
        source_dir: Path,
        entrypoint: str,
        manifest: Any,
        project_root: Path,
        host_context: Any,
        timeout_sec: float = 5.0,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.entrypoint = str(entrypoint)
        self.manifest = manifest
        self.project_root = Path(project_root)
        self.host_context = host_context
        self.timeout_sec = float(timeout_sec)
        self.status = "starting"
        self.error = ""
        self.restart_count = 0
        self._consecutive_failures = 0
        self._blocked = False
        self._manual_stopped = False
        self._next_id = 0
        self._lock = threading.RLock()
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._closed = False
        self._proc: subprocess.Popen[str] | None = None
        self._finalizer: weakref.finalize[Any] | None = None
        self._reader: threading.Thread | None = None
        self._start_worker(increment_restart_count=False)
        self._initialize_worker()
        self.status = "ready"

    @property
    def pid(self) -> int | None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return None
        return int(proc.pid)

    @property
    def last_error(self) -> str:
        return self.error

    @property
    def blocked(self) -> bool:
        return self._blocked

    @property
    def manual_restart_required(self) -> bool:
        return self._blocked or self._manual_stopped

    def _start_worker(self, *, increment_restart_count: bool) -> None:
        self._lines = queue.Queue()
        self._proc = self._start_process()
        if increment_restart_count:
            self.restart_count += 1
        self._finalizer = weakref.finalize(self, _terminate_process, self._proc)
        self._reader = threading.Thread(
            target=self._read_stdout,
            args=(self._proc, self._lines),
            name=f"extension-worker-reader-{self.source_dir.name}",
            daemon=True,
        )
        self._reader.start()

    def _initialize_worker(self) -> None:
        self._raw_call(
            "initialize",
            {
                "source_dir": str(self.source_dir),
                "entrypoint": self.entrypoint,
                "manifest": self._manifest_dict(self.manifest),
                "project_root": str(self.project_root),
                "chat_client_attrs": self._chat_client_attrs(),
                "has_docker_runtime": getattr(self.host_context, "docker_runtime", None) is not None,
                "metadata_callables": self._metadata_callables(),
            },
            timeout_sec=max(8.0, self.timeout_sec),
        )

    def _start_process(self) -> subprocess.Popen[str]:
        env = dict(os.environ)
        sandbox_root = Path(__file__).resolve().parents[1]
        core_modules_root = sandbox_root.parent
        repo_root = core_modules_root.parent
        paths = [
            str(self.project_root),
            str(repo_root),
            str(sandbox_root),
            str(core_modules_root / "LlmInteractor"),
            str(core_modules_root / "Security"),
            str(core_modules_root / "DockerManager"),
        ]
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([*paths, current] if current else paths)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return subprocess.Popen(
            [sys.executable, "-m", "extensions_sandbox.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(self.project_root),
            env=env,
        )

    def _read_stdout(self, proc: subprocess.Popen[str] | None, lines: queue.Queue[str | None]) -> None:
        if proc is None:
            lines.put(None)
            return
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    def _manifest_dict(self, manifest: Any) -> dict[str, Any]:
        if is_dataclass(manifest):
            data = to_jsonable(asdict(manifest))
            if isinstance(data, dict):
                metadata = data.pop("metadata", {})
                if isinstance(metadata, dict):
                    for key, value in metadata.items():
                        data.setdefault(str(key), value)
            return data
        return to_jsonable(manifest) if isinstance(manifest, dict) else {}

    def _chat_client_attrs(self) -> dict[str, Any]:
        chat = getattr(self.host_context, "chat_client", None)
        url = str(getattr(chat, "_url", "") or "") if chat is not None else ""
        model = str(getattr(chat, "_model", "") or "") if chat is not None else ""
        metadata = getattr(self.host_context, "metadata", {}) or {}
        if isinstance(metadata, dict):
            if not url:
                url = str(metadata.get("chat_url") or metadata.get("base_url") or "")
            if not model:
                model = str(metadata.get("default_chat_model") or metadata.get("chat_model") or "")
        return {"_url": url, "_model": model}

    def _metadata_callables(self) -> list[str]:
        metadata = getattr(self.host_context, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return []
        return sorted(str(key) for key, value in metadata.items() if callable(value))

    def _extension_id(self) -> str:
        manifest_id = getattr(self.manifest, "id", None)
        if manifest_id:
            return str(manifest_id)
        data = self._manifest_dict(self.manifest)
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return self.source_dir.name

    def _log_worker_restarting(
        self,
        *,
        trigger: str,
        reason: str = "",
        method: str = "",
        attempt: int = 0,
        error: str = "",
    ) -> None:
        attempt_text = f"{attempt}/{self.MAX_AUTO_RESTARTS}" if attempt > 0 else "-"
        _log.info(
            "extension worker restarting: extension=%s trigger=%s reason=%s method=%s attempt=%s error=%s",
            self._extension_id(),
            trigger,
            reason or "-",
            method or "-",
            attempt_text,
            (error or self.error or "-")[:200],
        )

    def _log_worker_restarted(self, *, trigger: str) -> None:
        _log.info(
            "extension worker restarted: extension=%s trigger=%s pid=%s restart_count=%s",
            self._extension_id(),
            trigger,
            self.pid or "not running",
            self.restart_count,
        )

    def _log_worker_blocked(self, *, method: str = "", error: str = "") -> None:
        _log.warning(
            "extension worker blocked until manual restart: extension=%s method=%s failures=%s error=%s",
            self._extension_id(),
            method or "-",
            self._consecutive_failures,
            (error or self.error or "-")[:200],
        )

    def call(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: float | None = None) -> Any:
        with self._lock:
            if self._blocked:
                raise ExtensionWorkerError(self.error or "extension worker is blocked until manual restart")
            if self._manual_stopped:
                raise ExtensionWorkerError("extension worker is stopped until manual restart")
            attempt = 0
            while True:
                try:
                    result = self._raw_call(method, params, timeout_sec=timeout_sec)
                    self.status = "ready"
                    self.error = ""
                    self._consecutive_failures = 0
                    return result
                except (ExtensionWorkerTimeout, ExtensionWorkerError):
                    if not self._should_auto_restart(method=method):
                        raise
                    attempt += 1
                    self._log_worker_restarting(
                        trigger="auto",
                        reason=self.status,
                        method=method,
                        attempt=attempt,
                        error=self.error,
                    )
                    self._restart_after_failure(trigger="auto")
                    if attempt > self.MAX_AUTO_RESTARTS:
                        raise

    def _raw_call(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: float | None = None) -> Any:
        with self._lock:
            if self._closed:
                raise ExtensionWorkerError("extension worker is closed")
            if self._proc is None:
                raise ExtensionWorkerError("extension worker is unavailable")
            if self._proc.poll() is not None:
                self.status = "crashed"
                self.error = self._stderr_tail()
                raise ExtensionWorkerError(f"extension worker exited with {self._proc.returncode}: {self.error}")
            req_id = self._next()
            self._write({"type": "request", "id": req_id, "method": method, "params": dict(params or {})})
            return self._wait_response(req_id, timeout_sec or self.timeout_sec)

    def _should_auto_restart(self, *, method: str = "") -> bool:
        if self._closed or self._blocked or self._manual_stopped:
            return False
        if self.status not in {"crashed", "timeout", "protocol_error"}:
            return False
        self._consecutive_failures += 1
        if self._consecutive_failures > self.MAX_AUTO_RESTARTS:
            self._blocked = True
            self.status = "blocked"
            if not self.error:
                self.error = "extension worker failed repeatedly and is blocked until manual restart"
            self._log_worker_blocked(method=method, error=self.error)
            return False
        return True

    def _restart_after_failure(self, *, trigger: str = "auto") -> None:
        previous_error = self.error
        self._shutdown_process()
        self.status = "restarting"
        try:
            self._start_worker(increment_restart_count=True)
            self._initialize_worker()
            self.status = "ready"
            self.error = ""
            self._manual_stopped = False
            self._log_worker_restarted(trigger=trigger)
        except Exception as e:
            self.status = "crashed"
            self.error = f"{type(e).__name__}: {e}" if str(e) else previous_error
            self._shutdown_process()
            raise

    def _next(self) -> int:
        self._next_id += 1
        return self._next_id

    def _write(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise ExtensionWorkerError("extension worker stdin is closed")
        try:
            self._proc.stdin.write(json.dumps(to_jsonable(payload), ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            # Worker process died between the poll() check and the write.
            self.status = "crashed"
            self.error = self._stderr_tail() or str(exc)
            raise ExtensionWorkerError(f"extension worker stdin broken: {exc}") from exc

    def _wait_response(self, req_id: int, timeout_sec: float) -> Any:
        deadline = time.monotonic() + float(timeout_sec)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.status = "timeout"
                self.error = f"worker call timed out: request {req_id}"
                raise ExtensionWorkerTimeout(self.error)
            try:
                line = self._lines.get(timeout=min(0.2, remaining))
            except queue.Empty:
                if self._proc is not None and self._proc.poll() is not None:
                    self.status = "crashed"
                    self.error = self._stderr_tail()
                    raise ExtensionWorkerError(f"extension worker exited with {self._proc.returncode}: {self.error}")
                continue
            if line is None:
                self.status = "crashed"
                self.error = self._stderr_tail()
                raise ExtensionWorkerError(f"extension worker closed stdout: {self.error}")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                self.status = "protocol_error"
                self.error = f"invalid worker JSON: {line[:200]}"
                raise ExtensionWorkerError(self.error) from e
            mtype = msg.get("type")
            if mtype == "host_call":
                self._handle_host_call(msg)
                continue
            if mtype != "response" or int(msg.get("id") or -1) != req_id:
                continue
            if msg.get("ok"):
                return msg.get("result")
            self.status = "error"
            self.error = str(msg.get("error") or "worker call failed")
            raise ExtensionWorkerError(self.error)

    def _handle_host_call(self, msg: dict[str, Any]) -> None:
        call_id = int(msg.get("id") or 0)
        try:
            result = self._dispatch_host_call_bounded(
                str(msg.get("target") or ""),
                str(msg.get("method") or ""),
                list(msg.get("args") or []),
                dict(msg.get("kwargs") or {}),
            )
            self._write({"type": "host_response", "id": call_id, "ok": True, "result": result})
        except Exception as e:
            self._write({"type": "host_response", "id": call_id, "ok": False, "error": f"{type(e).__name__}: {e}"})

    def _dispatch_host_call_bounded(self, target: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        timeout_sec = _HOST_CALL_TIMEOUTS.get((target, method))
        if not timeout_sec or timeout_sec <= 0:
            return self._dispatch_host_call(target, method, args, kwargs)

        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def _target() -> None:
            try:
                result_queue.put((True, self._dispatch_host_call(target, method, args, kwargs)))
            except BaseException as exc:  # pragma: no cover - re-raised in caller thread
                result_queue.put((False, exc))

        thread = threading.Thread(
            target=_target,
            name=f"extension-host-call-{target}-{method}",
            daemon=True,
        )
        thread.start()
        try:
            ok, value = result_queue.get(timeout=float(timeout_sec))
        except queue.Empty as exc:
            raise TimeoutError(
                f"host call {target}.{method} timed out after {float(timeout_sec):.1f}s"
            ) from exc
        if ok:
            return value
        raise value

    # Explicit allowlist for chat_client methods callable from sandboxed extensions.
    # docker_runtime already has an allowlist; this mirrors that pattern for chat.
    _CHAT_CLIENT_ALLOWED_METHODS: frozenset[str] = frozenset(
        {
            "chat",
            "chat_api",
            "chat_api_stream_final",
            "iter_chat_api_stream_events",
            "iter_chat_api_stream_openai_parts",
        }
    )

    def _dispatch_host_call(self, target: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if target == "settings":
            repo = self.host_context.get_settings_repository()
            key = str(args[0] if args else "")
            if method == "get_app_setting":
                return repo.get_app_setting(key)
            if method == "set_app_setting":
                # Writes are restricted to the extension-owned namespace to prevent
                # a sandboxed extension from overwriting host application settings.
                if not key.startswith("ext."):
                    raise PermissionError(
                        f"extension settings writes must use the 'ext.' namespace prefix; "
                        f"got key: {key!r}"
                    )
                repo.set_app_setting(key, args[1] if len(args) > 1 else "")
                return None
        if target == "chat_client":
            chat = getattr(self.host_context, "chat_client", None)
            if chat is None:
                raise RuntimeError("chat_client is unavailable")
            if method not in self._CHAT_CLIENT_ALLOWED_METHODS:
                raise AttributeError(f"chat_client method not allowed: {method!r}")
            fn = getattr(chat, method, None)
            if not callable(fn):
                raise AttributeError(f"chat_client method not found: {method!r}")
            result = fn(*args, **kwargs)
            if method.startswith("iter_") or not isinstance(result, (dict, str, int, float, bool, type(None), list)):
                try:
                    return list(result)
                except TypeError:
                    return result
            return result
        if target == "docker_runtime":
            docker = getattr(self.host_context, "docker_runtime", None)
            if docker is None:
                raise RuntimeError("docker_runtime is unavailable")
            allowed = {"ensure_container", "stop_container", "inspect_container", "wait_http", "check_image_update"}
            if method not in allowed:
                raise AttributeError(f"docker_runtime method not allowed: {method}")
            if method == "ensure_container" and args and isinstance(args[0], dict):
                from core.contracts.docker_runtime import DockerContainerSpec

                args = [DockerContainerSpec(**args[0]), *args[1:]]
            return getattr(docker, method)(*args, **kwargs)
        if target == "metadata":
            metadata = getattr(self.host_context, "metadata", {}) or {}
            fn = metadata.get(method) if isinstance(metadata, dict) else None
            if not callable(fn):
                raise AttributeError(f"metadata callable not allowed: {method}")
            return fn(*args, **kwargs)
        raise AttributeError(f"host target not allowed: {target}")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.status = "closed"
            self._shutdown_process(send_shutdown=True)

    def kill(self) -> None:
        with self._lock:
            if self._closed:
                raise ExtensionWorkerError("extension worker is closed")
            self._manual_stopped = True
            self._blocked = False
            self.status = "manual_stop"
            self.error = ""
            self._shutdown_process(send_shutdown=False)

    def restart(self) -> None:
        with self._lock:
            if self._closed:
                raise ExtensionWorkerError("extension worker is closed")
            self._blocked = False
            self._manual_stopped = False
            self._consecutive_failures = 0
            self.error = ""
            self.status = "restarting"
            self._log_worker_restarting(trigger="manual", reason="manual")
            self._shutdown_process(send_shutdown=False)
            self._start_worker(increment_restart_count=True)
            try:
                self._initialize_worker()
            except Exception as e:
                self.status = "crashed"
                self.error = f"{type(e).__name__}: {e}" if str(e) else self.error
                self._shutdown_process(send_shutdown=False)
                raise
            self.status = "ready"
            self._log_worker_restarted(trigger="manual")

    def _shutdown_process(self, *, send_shutdown: bool = False) -> None:
        proc = self._proc
        if proc is None:
            return
        if send_shutdown:
            try:
                if proc.poll() is None:
                    self._write({"type": "request", "id": self._next(), "method": "shutdown", "params": {}})
            except Exception:  # safe: shutdown request best-effort before terminate
                pass
        _terminate_process(proc)
        if self._finalizer is not None:
            self._finalizer.detach()
            self._finalizer = None
        self._proc = None

    def _stderr_tail(self) -> str:
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            return self._proc.stderr.read()[-1000:]
        except Exception:
            return ""


def namespace_from_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{k: namespace_from_dict(v) for k, v in value.items()})
    if isinstance(value, list):
        return [namespace_from_dict(item) for item in value]
    return value
