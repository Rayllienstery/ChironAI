"""Codex launcher helpers for ChironAI LLM Proxy builds."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

from application.llm_proxy_builds import (
    DEFAULT_NUM_PREDICT,
    LLM_PROXY_BUILDS_APP_KEY,
    find_build_by_id,
    load_builds_json,
)

CODEX_PROFILE_NAME = "chironai-proxy"
CODEX_PROVIDER_NAME = "ChironAI LLM Proxy"
CHIRONAI_CODEX_HOME = Path.home() / ".chironai" / "codex"
CODEX_MODEL_CATALOG_FILENAME = "models.json"
DEFAULT_CODEX_CONTEXT_WINDOW = 131072
CODEX_SANDBOX_MODE = "danger-full-access" if sys.platform == "win32" else "workspace-write"
CODEX_BASE_INSTRUCTIONS = (
    "You are Codex, a coding agent running through the ChironAI LLM Proxy. "
    "You and the user share one workspace; help complete coding tasks carefully."
)
CODEX_INSTRUCTIONS_TEMPLATE = CODEX_BASE_INSTRUCTIONS + "\n\n{{ personality }}"


class CodexLauncherError(RuntimeError):
    """Raised for user-actionable Codex launcher failures."""


def _proxy_api_key_module() -> Any:
    try:
        return importlib.import_module("llm_proxy.api_key")
    except Exception:
        path = Path(__file__).resolve().parents[2] / "CoreModules" / "LlmProxy" / "llm_proxy" / "api_key.py"
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


def _remove_section(text: str, header: str) -> str:
    idx = text.find(header)
    if idx < 0:
        return text
    rest = text[idx + len(header) :]
    end_idx = rest.find("\n[")
    if end_idx >= 0:
        return text[:idx] + rest[end_idx + 1 :]
    return text[:idx].rstrip() + ("\n" if text[:idx].strip() else "")


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value))


def codex_home() -> Path:
    return CHIRONAI_CODEX_HOME


def codex_config_path() -> Path:
    return codex_home() / "config.toml"


def codex_model_catalog_path(config_path: Path | None = None) -> Path:
    if config_path is not None:
        return config_path.parent / CODEX_MODEL_CATALOG_FILENAME
    return codex_home() / CODEX_MODEL_CATALOG_FILENAME


def _positive_int(value: Any, *, default: int, minimum: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= minimum else default


def codex_model_catalog_entry(build: dict[str, Any]) -> dict[str, Any]:
    build_id = str(build.get("id") or "").strip()
    display_name = str(build.get("display_name") or build_id).strip() or build_id
    context_window = _positive_int(
        build.get("num_ctx") or build.get("context_length"),
        default=DEFAULT_CODEX_CONTEXT_WINDOW,
        minimum=256,
    )
    max_output_tokens = _positive_int(
        build.get("num_predict"),
        default=DEFAULT_NUM_PREDICT,
        minimum=1,
    )
    max_output_tokens = min(max_output_tokens, max(1, context_window - 1))
    upstream_model = str(build.get("model") or build.get("ollama_model") or "").strip()
    description = (
        f"ChironAI IDE build backed by {upstream_model}."
        if upstream_model
        else "ChironAI IDE build."
    )
    return {
        "prefer_websockets": False,
        "support_verbosity": False,
        "default_verbosity": None,
        "slug": build_id,
        "display_name": display_name,
        "description": description,
        "default_reasoning_level": None,
        "supported_reasoning_levels": [],
        "context_window": context_window,
        "max_context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "auto_compact_token_limit": None,
        "apply_patch_tool_type": "freeform",
        "web_search_tool_type": "text",
        "shell_type": "shell_command",
        "input_modalities": ["text", "image"],
        "supports_image_detail_original": True,
        "truncation_policy": {"mode": "tokens", "limit": 10000},
        "supports_parallel_tool_calls": True,
        "reasoning_summary_format": "none",
        "default_reasoning_summary": "none",
        "visibility": "list",
        "minimal_client_version": "0.0.1",
        "supported_in_api": True,
        "availability_nux": None,
        "upgrade": None,
        "priority": 100,
        "base_instructions": CODEX_BASE_INSTRUCTIONS,
        "model_messages": {
            "instructions_template": CODEX_INSTRUCTIONS_TEMPLATE,
            "instructions_variables": {
                "personality_default": "",
                "personality_pragmatic": (
                    "# Personality\n\n"
                    "You are concise, practical, and careful. Keep the user informed, "
                    "use tools deliberately, and verify important coding changes."
                ),
            },
        },
        "supports_reasoning_summaries": False,
        "effective_context_window_percent": 95,
        "experimental_supported_tools": [],
        "available_in_plans": [],
        "supports_search_tool": True,
        "service_tiers": [],
        "additional_speed_tiers": [],
    }


def write_codex_model_catalog(
    builds: list[dict[str, Any]],
    *,
    catalog_path: Path | None = None,
) -> Path:
    target = catalog_path or codex_model_catalog_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        codex_model_catalog_entry(build)
        for build in builds
        if str(build.get("id") or "").strip()
    ]
    data = {"models": sorted(entries, key=lambda item: str(item.get("slug") or "").lower())}
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def write_codex_profile(
    base_url: str,
    *,
    config_path: Path | None = None,
    build: dict[str, Any] | None = None,
    builds: list[dict[str, Any]] | None = None,
) -> Path:
    target = config_path
    if target is None:
        target = codex_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized_base = base_url.rstrip("/") + "/"
    catalog_builds = list(builds or ([] if build is None else [build]))
    catalog_path = None
    if catalog_builds:
        catalog_path = write_codex_model_catalog(
            catalog_builds,
            catalog_path=codex_model_catalog_path(target),
        )

    profile_lines = [
        'forced_login_method = "api"',
        f'model_provider = "{CODEX_PROFILE_NAME}"',
        f'sandbox_mode = "{CODEX_SANDBOX_MODE}"',
    ]
    if build:
        build_id = str(build.get("id") or "").strip()
        if build_id:
            profile_lines.append(f"model = {_toml_string(build_id)}")
    if catalog_path is not None:
        profile_lines.append(f"model_catalog_json = {_toml_string(catalog_path.resolve())}")

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
    text = _remove_section(text, f"[profiles.{CODEX_PROFILE_NAME}.windows]")
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
