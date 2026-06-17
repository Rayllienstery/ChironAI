"""
Ollama HTTP client for the ollama-provider extension.

Self-contained: uses OllamaInteractor (HTTP helpers or subprocess CLI) to call
the Ollama REST API.  No imports from infrastructure.* or domain.*.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

import requests


class OllamaHttpError(Exception):
    """CLI exited non-zero or produced invalid output."""

    def __init__(self, message: str, *, stderr: str = "", returncode: int | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def _find_repo_root() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(16):
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


def _cli_error_message(detail: dict[str, Any], fallback: str) -> str:
    msg = detail.get("error") or fallback
    body = detail.get("body")
    if isinstance(body, dict):
        oerr = body.get("error")
        if oerr is not None and str(oerr).strip():
            return f"{msg} — Ollama: {oerr}" if msg else str(oerr)
    return msg or fallback


def _invoke(
    argv_suffix: list[str],
    *,
    stdin_obj: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> tuple[str, str]:
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
        raise OllamaHttpError(f"ollama_interactor timeout: {e}") from e
    if proc.returncode != 0:
        detail = _parse_stderr_json(proc.stderr) or {}
        msg = _cli_error_message(detail, proc.stderr.strip() or f"exit {proc.returncode}")
        raise OllamaHttpError(msg, stderr=proc.stderr, returncode=proc.returncode)
    return proc.stdout, proc.stderr


def _invoke_json(
    argv_suffix: list[str],
    *,
    stdin_obj: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    out, _ = _invoke(argv_suffix, stdin_obj=stdin_obj, timeout=timeout)
    out = out.strip()
    if not out:
        raise OllamaHttpError("empty stdout from ollama_interactor")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise OllamaHttpError(f"invalid JSON stdout: {out[:500]}") from e


def _ollama_interactor_http_module() -> Any | None:
    """Import ``ollama_interactor.ollama_http`` using repo-local package path, or None."""
    idir = _interactor_pythonpath_dir()
    if not idir:
        return None
    try:
        if idir not in sys.path:
            sys.path.insert(0, idir)
        from ollama_interactor import ollama_http as oh  # noqa: PLC0415

        return oh
    except Exception:  # safe: optional ollama_interactor import; CLI fallback used
        return None


def invoke_ping(*, base_url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Ping Ollama via OllamaInteractor HTTP helpers, else CLI."""
    oh = _ollama_interactor_http_module()
    if oh is not None:
        try:
            return oh.ping(base_url.rstrip("/"), timeout=timeout)
        except Exception:  # safe: HTTP helper failed; fall back to CLI invoke
            pass
    return _invoke_json(
        ["ping", "--base-url", base_url, "--timeout", str(timeout)],
        timeout=timeout + 5.0,
    )


def invoke_tags(*, base_url: str, timeout: float = 30.0) -> dict[str, Any]:
    """GET Ollama ``/api/tags`` via OllamaInteractor HTTP helpers, else CLI."""
    oh = _ollama_interactor_http_module()
    if oh is not None:
        try:
            return oh.get_tags(base_url.rstrip("/"), timeout=timeout)
        except Exception:  # safe: HTTP helper failed; fall back to CLI invoke
            pass
    return _invoke_json(
        ["tags", "--base-url", base_url, "--timeout", str(timeout)],
        timeout=timeout + 5.0,
    )


def invoke_raw_json(
    *,
    base_url: str,
    api_segment: str,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """Forward a raw Ollama-compatible JSON request."""
    base = base_url.rstrip("/")
    segment = api_segment.strip().lstrip("/")
    url = f"{base}/api/{segment}"
    retries = max(0, _env_int("OLLAMA_CHAT_MAX_RETRIES", 2))
    base_delay = _env_float("OLLAMA_CHAT_RETRY_BASE_SEC", 1.0)
    attempts = max(1, retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            if method.upper() == "GET":
                resp = requests.get(url, params=params or {}, timeout=timeout, headers=headers or None)
            else:
                resp = requests.request(
                    method.upper(),
                    url,
                    json=dict(body or {}),
                    timeout=timeout,
                    headers=headers or None,
                )
            resp.raise_for_status()
            try:
                return resp.json()
            finally:
                resp.close()
        except requests.HTTPError as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not _requests_error_is_transient(exc):
                raise
            time.sleep(max(0.1, float(base_delay)) * (2**attempt))
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not _requests_error_is_transient(exc):
                raise
            time.sleep(max(0.1, float(base_delay)) * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise OllamaHttpError("invoke_raw_json: unreachable")


def iter_raw_lines(
    *,
    base_url: str,
    api_segment: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
    read_timeout: float = 86400.0,
) -> Iterator[str]:
    """Forward a raw Ollama-compatible streaming request and yield NDJSON lines."""
    url = f"{base_url.rstrip('/')}/api/{api_segment.strip().lstrip('/')}"
    retries = max(0, _env_int("OLLAMA_CHAT_MAX_RETRIES", 2))
    base_delay = _env_float("OLLAMA_CHAT_RETRY_BASE_SEC", 1.0)
    attempts = max(1, retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            resp = requests.post(
                url,
                json=dict(body or {}),
                timeout=(30.0, max(float(read_timeout), 60.0)),
                stream=True,
                headers=headers or None,
            )
            resp.raise_for_status()
            try:
                for line in resp.iter_lines(decode_unicode=True):
                    if line:
                        yield str(line)
            finally:
                resp.close()
            return
        except requests.HTTPError as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not _requests_error_is_transient(exc):
                raise
            time.sleep(max(0.1, float(base_delay)) * (2**attempt))
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= attempts - 1 or not _requests_error_is_transient(exc):
                raise
            time.sleep(max(0.1, float(base_delay)) * (2**attempt))
    if last_exc is not None:
        raise last_exc
    raise OllamaHttpError("iter_raw_lines: unreachable")


def invoke_show(*, base_url: str, name: str, timeout: float = 120.0) -> dict[str, Any]:
    """POST Ollama ``/api/show`` via OllamaInteractor HTTP helpers, else CLI."""
    oh = _ollama_interactor_http_module()
    if oh is not None:
        try:
            return oh.post_show(base_url.rstrip("/"), name, timeout=timeout)
        except Exception:  # safe: HTTP helper failed; fall back to CLI invoke
            pass
    return _invoke_json(
        ["show", "--base-url", base_url.rstrip("/"), "--name", name, "--timeout", str(timeout)],
        timeout=timeout + 30.0,
    )


def invoke_delete(*, base_url: str, name: str, timeout: float = 120.0) -> dict[str, Any]:
    """POST Ollama ``/api/delete`` via OllamaInteractor HTTP helpers, else CLI."""
    oh = _ollama_interactor_http_module()
    if oh is not None:
        try:
            return oh.post_delete(base_url.rstrip("/"), name, timeout=timeout)
        except Exception:  # safe: HTTP helper failed; fall back to CLI invoke
            pass
    return _invoke_json(
        ["delete", "--base-url", base_url.rstrip("/"), "--name", name, "--timeout", str(timeout)],
        timeout=timeout + 30.0,
    )


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _requests_error_is_transient(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in (500, 502, 503, 504):
        return True
    blob = str(exc).lower()
    if "timeout" in blob:
        return True
    return any(
        token in blob
        for token in (
            "connection refused",
            "connection reset",
            "temporarily unavailable",
            "econnrefused",
            "503 server error",
            "502 server error",
            "504 server error",
        )
    )


def _embed_error_is_transient(err: OllamaHttpError) -> bool:
    stderr = err.stderr or ""
    blob = f"{stderr}\n{err!s}".lower()
    if "timeout" in blob:
        return True
    if any(x in blob for x in ("connection refused", "connection reset", "temporarily unavailable", "econnrefused")):
        return True
    if any(code in stderr for code in ("500", "502", "503", "504")):
        return True
    detail = _parse_stderr_json(stderr)
    if isinstance(detail, dict):
        body = detail.get("body")
        if isinstance(body, dict):
            sc = body.get("status_code")
            if sc is not None and str(sc) in ("500", "502", "503", "504"):
                return True
    return False


def invoke_embed(
    stdin_obj: dict[str, Any],
    *,
    default_timeout: float = 120.0,
    max_retries: int | None = None,
    retry_base_delay_sec: float | None = None,
) -> dict[str, Any]:
    """Call Ollama embed via ollama_interactor with optional retry on transient errors."""
    t = float(stdin_obj.get("timeout", default_timeout))
    cli_t = max(1, int(t))
    timeout_budget = t + max(90.0, t * 0.25)
    retries = max_retries if max_retries is not None else _env_int("RAG_EMBED_MAX_RETRIES", 0)
    base_delay = retry_base_delay_sec if retry_base_delay_sec is not None else _env_float("RAG_EMBED_RETRY_BASE_SEC", 1.0)
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            return _invoke_json(["embed", "--timeout", str(cli_t)], stdin_obj=stdin_obj, timeout=timeout_budget)
        except OllamaHttpError as e:
            if attempt >= attempts - 1 or not _embed_error_is_transient(e):
                raise
            time.sleep(max(0.1, float(base_delay)) * (2**attempt))
    raise OllamaHttpError("invoke_embed: unreachable")


def invoke_generate(stdin_obj: dict[str, Any], *, default_timeout: float = 120.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return _invoke_json(["generate", "--timeout", str(default_timeout)], stdin_obj=stdin_obj, timeout=t + 30.0)


def invoke_rerank(stdin_obj: dict[str, Any], *, default_timeout: float = 120.0) -> dict[str, Any]:
    t = float(stdin_obj.get("timeout", default_timeout))
    return _invoke_json(["rerank", "--timeout", str(default_timeout)], stdin_obj=stdin_obj, timeout=t + 30.0)


def iter_pull_objects(
    *,
    base_url: str,
    name: str,
    insecure: bool = False,
    read_timeout: float = 86400.0,
) -> Iterator[dict[str, Any]]:
    """Stream Ollama ``/api/pull`` progress as dicts."""
    oh = _ollama_interactor_http_module()
    pull_timeout = (30.0, max(float(read_timeout), 60.0))
    if oh is not None:
        yield from oh.stream_pull_objects(
            base_url.rstrip("/"),
            name,
            insecure=insecure,
            timeout=pull_timeout,
        )
        return

    argv = ["pull", "--base-url", base_url.rstrip("/"), "--name", name, "--timeout", str(max(read_timeout, 60.0))]
    if insecure:
        argv.append("--insecure")
    wait_timeout = max(float(read_timeout) + 120.0, 300.0)
    cmd, env = _build_command(argv)
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    assert proc.stdout is not None

    def _gen() -> Iterator[dict[str, Any]]:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
        finally:
            try:
                code = proc.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait(timeout=10)
            err = proc.stderr.read() if proc.stderr else ""
            if code != 0:
                detail = _parse_stderr_json(err) or {}
                msg = _cli_error_message(detail, err.strip() or f"exit {code}")
                raise OllamaHttpError(msg, stderr=err, returncode=code)

    yield from _gen()


__all__ = [
    "OllamaHttpError",
    "invoke_delete",
    "invoke_embed",
    "invoke_generate",
    "invoke_ping",
    "invoke_rerank",
    "invoke_raw_json",
    "invoke_show",
    "invoke_tags",
    "iter_raw_lines",
    "iter_pull_objects",
]
