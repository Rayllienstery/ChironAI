"""Host-side client for extension worker processes."""

from __future__ import annotations

import json
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


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class ExtensionWorkerClient:
    """Line-delimited JSON RPC client for one extension worker."""

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
        self._next_id = 0
        self._lock = threading.RLock()
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._closed = False
        self._proc = self._start_process()
        self._finalizer = weakref.finalize(self, _terminate_process, self._proc)
        self._reader = threading.Thread(target=self._read_stdout, name=f"extension-worker-reader-{self.source_dir.name}", daemon=True)
        self._reader.start()
        self.call(
            "initialize",
            {
                "source_dir": str(self.source_dir),
                "entrypoint": self.entrypoint,
                "manifest": self._manifest_dict(manifest),
                "project_root": str(self.project_root),
                "chat_client_attrs": self._chat_client_attrs(),
                "has_docker_runtime": getattr(host_context, "docker_runtime", None) is not None,
                "metadata_callables": self._metadata_callables(),
            },
            timeout_sec=max(8.0, self.timeout_sec),
        )
        self.status = "ready"

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

    def _read_stdout(self) -> None:
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._lines.put(line)
        finally:
            self._lines.put(None)

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
        if chat is None:
            return {}
        return {
            "_url": str(getattr(chat, "_url", "") or ""),
            "_model": str(getattr(chat, "_model", "") or ""),
        }

    def _metadata_callables(self) -> list[str]:
        metadata = getattr(self.host_context, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            return []
        return sorted(str(key) for key, value in metadata.items() if callable(value))

    def call(self, method: str, params: dict[str, Any] | None = None, *, timeout_sec: float | None = None) -> Any:
        with self._lock:
            if self._closed:
                raise ExtensionWorkerError("extension worker is closed")
            if self._proc.poll() is not None:
                self.status = "crashed"
                self.error = self._stderr_tail()
                raise ExtensionWorkerError(f"extension worker exited with {self._proc.returncode}: {self.error}")
            req_id = self._next()
            self._write({"type": "request", "id": req_id, "method": method, "params": dict(params or {})})
            return self._wait_response(req_id, timeout_sec or self.timeout_sec)

    def _next(self) -> int:
        self._next_id += 1
        return self._next_id

    def _write(self, payload: dict[str, Any]) -> None:
        if self._proc.stdin is None:
            raise ExtensionWorkerError("extension worker stdin is closed")
        self._proc.stdin.write(json.dumps(to_jsonable(payload), ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

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
                if self._proc.poll() is not None:
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
            result = self._dispatch_host_call(
                str(msg.get("target") or ""),
                str(msg.get("method") or ""),
                list(msg.get("args") or []),
                dict(msg.get("kwargs") or {}),
            )
            self._write({"type": "host_response", "id": call_id, "ok": True, "result": result})
        except Exception as e:
            self._write({"type": "host_response", "id": call_id, "ok": False, "error": f"{type(e).__name__}: {e}"})

    def _dispatch_host_call(self, target: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if target == "settings":
            repo = self.host_context.get_settings_repository()
            if method == "get_app_setting":
                return repo.get_app_setting(str(args[0] if args else ""))
            if method == "set_app_setting":
                repo.set_app_setting(str(args[0] if args else ""), args[1] if len(args) > 1 else "")
                return None
        if target == "chat_client":
            chat = getattr(self.host_context, "chat_client", None)
            if chat is None:
                raise RuntimeError("chat_client is unavailable")
            fn = getattr(chat, method, None)
            if not callable(fn):
                raise AttributeError(f"chat_client method not allowed: {method}")
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
            allowed = {"ensure_container", "stop_container", "inspect_container", "wait_http"}
            if method not in allowed:
                raise AttributeError(f"docker_runtime method not allowed: {method}")
            if method == "ensure_container" and args and isinstance(args[0], dict):
                from docker_manager import DockerContainerSpec

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
            try:
                if self._proc.poll() is None:
                    self._write({"type": "request", "id": self._next(), "method": "shutdown", "params": {}})
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._finalizer.detach()

    def _stderr_tail(self) -> str:
        if self._proc.stderr is None:
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
