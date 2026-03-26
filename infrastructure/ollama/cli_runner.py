"""
Invoke CoreModules/OllamaInteractor CLI via subprocess.

Host code must not `import ollama_interactor`. Configuration:
- Default: ``sys.executable -m ollama_interactor`` with PYTHONPATH including
  ``<repo>/CoreModules/OllamaInteractor`` when that layout exists.
- Override: set ``OLLAMA_INTERACTOR_CMD`` to a shell-quoted prefix, e.g.
  ``C:\\Python311\\python.exe -m ollama_interactor`` or ``ollama-interactor``.
  When set, PYTHONPATH is not modified by this module.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Iterator
from typing import Any


class OllamaInteractorCliError(Exception):
    """CLI exited non-zero or produced invalid output."""

    def __init__(self, message: str, *, stderr: str = "", returncode: int | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def _find_repo_root() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(12):
        marker = os.path.join(cur, "CoreModules", "OllamaInteractor", "ollama_interactor", "__init__.py")
        if os.path.isfile(marker):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def _interactor_pythonpath_dir() -> str | None:
    root = _find_repo_root()
    if not root:
        return None
    d = os.path.join(root, "CoreModules", "OllamaInteractor")
    return d if os.path.isdir(d) else None


def _split_interactor_cmd() -> list[str] | None:
    raw = (os.environ.get("OLLAMA_INTERACTOR_CMD") or "").strip()
    if not raw:
        return None
    posix = os.name != "nt"
    return shlex.split(raw, posix=posix)


def _build_command(argv_suffix: list[str]) -> tuple[list[str], dict[str, str]]:
    env = dict(os.environ)
    custom = _split_interactor_cmd()
    if custom:
        return custom + argv_suffix, env
    cmd = [sys.executable, "-m", "ollama_interactor"] + argv_suffix
    idir = _interactor_pythonpath_dir()
    if idir:
        prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = idir + (os.pathsep + prev if prev else "")
    return cmd, env


def _parse_stderr_json(stderr: str) -> dict[str, Any] | None:
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def invoke(
    argv_suffix: list[str],
    *,
    stdin_obj: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> tuple[str, str]:
    """
    Run CLI; return (stdout, stderr).
    Raises OllamaInteractorCliError on non-zero exit.
    """
    cmd, env = _build_command(argv_suffix)
    inp = json.dumps(stdin_obj) if stdin_obj is not None else None
    try:
        proc = subprocess.run(
            cmd,
            input=inp,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise OllamaInteractorCliError(f"ollama_interactor timeout: {e}") from e
    if proc.returncode != 0:
        detail = _parse_stderr_json(proc.stderr) or {}
        msg = detail.get("error") or proc.stderr.strip() or f"exit {proc.returncode}"
        raise OllamaInteractorCliError(
            msg,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
    return proc.stdout, proc.stderr


def invoke_json(
    argv_suffix: list[str],
    *,
    stdin_obj: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    out, _ = invoke(argv_suffix, stdin_obj=stdin_obj, timeout=timeout)
    out = out.strip()
    if not out:
        raise OllamaInteractorCliError("empty stdout from ollama_interactor")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise OllamaInteractorCliError(f"invalid JSON stdout: {out[:500]}") from e


def invoke_tags(*, base_url: str, timeout: float = 30.0) -> dict[str, Any]:
    return invoke_json(
        ["tags", "--base-url", base_url, "--timeout", str(timeout)],
        timeout=timeout + 5.0,
    )


def invoke_ping(*, base_url: str, timeout: float = 5.0) -> dict[str, Any]:
    return invoke_json(
        ["ping", "--base-url", base_url, "--timeout", str(timeout)],
        timeout=timeout + 5.0,
    )


def invoke_embed(stdin_obj: dict[str, Any], *, default_timeout: float = 120.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return invoke_json(
        ["embed", "--timeout", str(default_timeout)],
        stdin_obj=stdin_obj,
        timeout=t + 30.0,
    )


def invoke_chat(stdin_obj: dict[str, Any], *, default_timeout: float = 600.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return invoke_json(
        ["chat", "--timeout", str(default_timeout)],
        stdin_obj=stdin_obj,
        timeout=t + 30.0,
    )


def invoke_generate(stdin_obj: dict[str, Any], *, default_timeout: float = 120.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return invoke_json(
        ["generate", "--timeout", str(default_timeout)],
        stdin_obj=stdin_obj,
        timeout=t + 30.0,
    )


def invoke_rerank(stdin_obj: dict[str, Any], *, default_timeout: float = 120.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return invoke_json(
        ["rerank", "--timeout", str(default_timeout)],
        stdin_obj=stdin_obj,
        timeout=t + 30.0,
    )


def iter_chat_stream(stdin_obj: dict[str, Any], *, default_timeout: float = 600.0) -> Iterator[str]:
    """
    Run chat-stream; yield content fragments from each stdout NDJSON line.
    """
    wait_timeout = max(float(stdin_obj.get("timeout", default_timeout)) + 60.0, 120.0)
    cmd, env = _build_command(["chat-stream", "--timeout", str(default_timeout)])
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps(stdin_obj))
    proc.stdin.close()

    def _gen() -> Iterator[str]:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                c = obj.get("content", "")
                if c:
                    yield c
        finally:
            try:
                code = proc.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait(timeout=10)
            err = proc.stderr.read() if proc.stderr else ""
            if code != 0:
                detail = _parse_stderr_json(err) or {}
                msg = detail.get("error") or err.strip() or f"exit {code}"
                raise OllamaInteractorCliError(msg, stderr=err, returncode=code)

    yield from _gen()


__all__ = [
    "OllamaInteractorCliError",
    "invoke",
    "invoke_chat",
    "invoke_embed",
    "invoke_generate",
    "invoke_json",
    "invoke_ping",
    "invoke_rerank",
    "invoke_tags",
    "iter_chat_stream",
]
