"""Codex launcher helpers for ChironAI LLM Proxy builds."""

from __future__ import annotations

import os
import importlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import requests

from application.llm_proxy_builds import LLM_PROXY_BUILDS_APP_KEY, find_build_by_id, load_builds_json

CODEX_PROFILE_NAME = "chironai-proxy"
CODEX_PROVIDER_NAME = "ChironAI LLM Proxy"
CHIRONAI_CODEX_HOME = Path.home() / ".chironai" / "codex"


class CodexLauncherError(RuntimeError):
    """Raised for user-actionable Codex launcher failures."""


def _proxy_api_key_module() -> Any:
    try:
        return importlib.import_module("llm_proxy.api_key")
    except Exception:
        path = Path(__file__).resolve().parents[1] / "CoreModules" / "LlmProxy" / "llm_proxy" / "api_key.py"
        spec = importlib.util.spec_from_file_location("_chironai_llm_proxy_api_key", path)
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


def proxy_base_url(port: int, *, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{int(port)}/v1/"


def load_builds(settings_repo: Any) -> list[dict[str, Any]]:
    raw = settings_repo.get_app_setting(LLM_PROXY_BUILDS_APP_KEY)
    return load_builds_json(raw)


def _is_ide_build(build: dict[str, Any]) -> bool:
    return bool(build.get("ide_mode")) or build.get("use_prompt_template") is False


def ide_builds(builds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in builds if _is_ide_build(item)]


def selected_ide_build(builds: list[dict[str, Any]], build_id: str) -> dict[str, Any]:
    build = find_build_by_id(builds, build_id)
    if build is None:
        raise CodexLauncherError(f"Build '{build_id}' was not found")
    if not _is_ide_build(build):
        raise CodexLauncherError(f"Build '{build_id}' is not enabled for IDE mode")
    return dict(build)


def proxy_key_status(settings_repo: Any) -> dict[str, Any]:
    return dict(_proxy_api_key_module().proxy_api_key_status(settings_repo))


def reveal_existing_proxy_key(settings_repo: Any) -> str:
    api_key_module = _proxy_api_key_module()
    status = api_key_module.proxy_api_key_status(settings_repo)
    if not bool(status.get("configured")):
        raise CodexLauncherError(
            "ChironAI Proxy API key is not configured. Create it in WebUI: RAG Fusion Proxy -> Overview -> Security."
        )
    if not bool(status.get("recoverable")):
        raise CodexLauncherError(
            "ChironAI Proxy API key is not recoverable. Regenerate it in WebUI: RAG Fusion Proxy -> Overview -> Security."
        )
    key = api_key_module.reveal_proxy_api_key(settings_repo).strip()
    if not key:
        raise CodexLauncherError(
            "ChironAI Proxy API key could not be revealed. Regenerate it in WebUI: RAG Fusion Proxy -> Overview -> Security."
        )
    return key


def check_proxy_reachable(base_url: str, api_key: str, *, timeout: float = 2.0) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/models"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    except requests.RequestException as exc:
        raise CodexLauncherError(f"ChironAI proxy is not reachable at {url}. Run: chironai proxy") from exc
    if response.status_code != 200:
        raise CodexLauncherError(f"ChironAI proxy returned HTTP {response.status_code} at {url}. Run: chironai proxy")
    data = response.json()
    return data if isinstance(data, dict) else {}


def _find_openai_codex_path() -> str:
    """Return the path to the OpenAI Codex CLI, skipping ChironAI's own codex wrapper."""
    candidates: list[str] = []

    # On Windows, npm installs into %APPDATA%\npm — check that first.
    if sys.platform == "win32":
        npm_bin = _npm_global_bin()
        if npm_bin:
            for name in ("codex.cmd", "codex"):
                p = Path(npm_bin) / name
                if p.exists():
                    candidates.append(str(p))

    # Fall back to whatever shutil.which finds.
    for name in ("codex", "codex.cmd", "codex.ps1"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)

    # Skip paths that belong to ChironAI's own bin directory.
    chironai_bin = str(CHIRONAI_CODEX_HOME.parent / "bin").lower()
    for p in candidates:
        if chironai_bin not in p.lower():
            return p

    return candidates[0] if candidates else ""


def _npm_global_bin() -> str:
    """Return the npm global bin directory, or empty string on failure."""
    try:
        out = subprocess.run(
            "npm bin -g",
            capture_output=True, text=True, timeout=5, shell=True, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def codex_status() -> dict[str, Any]:
    path = _find_openai_codex_path()
    if not path:
        return {"installed": False, "path": "", "version": ""}
    use_shell = sys.platform == "win32"
    cmd: Any = f'"{path}" --version' if use_shell else [path, "--version"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False, shell=use_shell)
        version = (out.stdout or out.stderr or "").strip()
        if out.returncode != 0:
            return {
                "installed": False,
                "path": path,
                "version": version,
                "error": "codex --version failed; command on PATH may not be OpenAI Codex CLI",
            }
    except Exception as e:
        return {"installed": False, "path": path, "version": "", "error": str(e)}
    return {"installed": True, "path": path, "version": version}


def require_codex_installed() -> None:
    status = codex_status()
    if not status.get("installed"):
        detail = str(status.get("error") or "").strip()
        path = str(status.get("path") or "").strip()
        suffix = f" Found: {path} ({detail})" if path else ""
        raise CodexLauncherError(f"Codex is not installed or is not the OpenAI Codex CLI. Install with: npm install -g @openai/codex{suffix}")


def _section_block(header: str, lines: list[str]) -> str:
    return "\n".join([header, *lines]) + "\n"


def codex_home() -> Path:
    return CHIRONAI_CODEX_HOME


def codex_config_path() -> Path:
    return codex_home() / "config.toml"


def write_codex_profile(
    base_url: str,
    *,
    config_path: Path | None = None,
    build: dict[str, Any] | None = None,
) -> Path:
    target = config_path
    if target is None:
        target = codex_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized_base = base_url.rstrip("/") + "/"

    profile_lines = [
        'forced_login_method = "api"',
        f'model_provider = "{CODEX_PROFILE_NAME}"',
        'sandbox_mode = "workspace-write"',
    ]
    if build:
        ctx = build.get("num_ctx") or build.get("context_length")
        if ctx:
            try:
                profile_lines.append(f"model_context_window = {int(ctx)}")
            except (ValueError, TypeError):
                pass

    sections = [
        (f"[profiles.{CODEX_PROFILE_NAME}]", profile_lines),
        (
            f"[model_providers.{CODEX_PROFILE_NAME}]",
            [
                f'name = "{CODEX_PROVIDER_NAME}"',
                f'base_url = "{normalized_base}"',
                'wire_api = "responses"',
                'env_key = "OPENAI_API_KEY"',
            ],
        ),
    ]
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    for header, lines in sections:
        block = _section_block(header, lines)
        idx = text.find(header)
        if idx >= 0:
            rest = text[idx + len(header) :]
            end_idx = rest.find("\n[")
            if end_idx >= 0:
                text = text[:idx] + block + rest[end_idx + 1 :]
            else:
                text = text[:idx] + block
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            if text:
                text += "\n"
            text += block
    target.write_text(text, encoding="utf-8")
    return target


def build_codex_argv(model: str, extra_args: list[str] | None = None) -> list[str]:
    codex_path = _find_openai_codex_path() or "codex"
    argv = [codex_path, "--profile", CODEX_PROFILE_NAME]
    if model:
        argv.extend(["-m", model])
    argv.extend(extra_args or [])
    return argv


def build_codex_env(api_key: str) -> dict[str, str]:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["CODEX_HOME"] = str(codex_home())
    return env


def build_command_preview(build_id: str) -> str:
    return f"chironai codex --model {build_id}"
