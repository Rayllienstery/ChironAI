"""Update ~/.config/opencode/opencode.jsonc for ChironAI vision."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

VISION_MODEL_FIELDS: dict[str, Any] = {
    "attachment": True,
    "tool_call": True,
    "modalities": {
        "input": ["text", "image"],
        "output": ["text"],
    },
}

# OpenCode picker: Hermes Smart/Flash plus three direct ChironAI builds.
CHIRON_OPENCODE_MODELS: dict[str, dict[str, Any]] = {
    "Hard-worker": {"name": "Kimi 2.7 Code", "reasoning_effort": "high"},
    "Hard-worker-2": {"name": "GLM 5.3", "reasoning_effort": "high"},
    "Flash-worker": {"name": "GLM 5.3 Flash", "reasoning_effort": "medium"},
}

HERMES_OPENCODE_MODELS: dict[str, dict[str, Any]] = {
    "hermes-smart": {"name": "Hermes Smart", "context": 1048576},
    "hermes-flash": {"name": "Hermes Flash", "context": 1048576},
}


def _hermes_env_path() -> Path:
    local = os.getenv("LOCALAPPDATA")
    if local:
        return Path(local) / "hermes" / ".env"
    return Path.home() / "AppData" / "Local" / "hermes" / ".env"


def _load_hermes_api_key() -> str:
    env_key = (os.getenv("HERMES_API_SERVER_KEY") or os.getenv("API_SERVER_KEY") or "").strip()
    if env_key:
        return env_key
    env_path = _hermes_env_path()
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_SERVER_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _default_hermes_base_url() -> str:
    return "http://127.0.0.1:8642/v1"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_db_path() -> Path:
    env_path = os.getenv("WEBUI_DB_PATH")
    if env_path:
        return Path(env_path)
    return _project_root() / "logs" / "webui.db"


def _default_output_path() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.jsonc"


def _default_base_url() -> str:
    return "http://127.0.0.1:8080/v1"


def _vision_model(
    name: str,
    *,
    context: int = 131072,
    output: int = 16384,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        **VISION_MODEL_FIELDS,
        "limit": {"context": context, "output": output},
    }
    if reasoning_effort:
        row["reasoning"] = True
        row["variants"] = {
            "low": {"reasoningEffort": "low"},
            "medium": {"reasoningEffort": "medium"},
            "high": {"reasoningEffort": "high"},
        }
        row["options"] = {"reasoningEffort": reasoning_effort}
    return row


def build_opencode_config(
    *,
    builds: list[dict[str, Any]],
    api_key: str,
    base_url: str,
    hermes_api_key: str = "",
    hermes_base_url: str = "",
) -> dict[str, Any]:
    by_id = {str(b.get("id") or "").strip(): b for b in builds if isinstance(b, dict)}
    models: dict[str, Any] = {}
    for build_id, meta in CHIRON_OPENCODE_MODELS.items():
        build = by_id.get(build_id) or {}
        try:
            ctx = int(build.get("num_ctx") or 131072)
        except (TypeError, ValueError):
            ctx = 131072
        try:
            out = int(build.get("num_predict") or 16384)
        except (TypeError, ValueError):
            out = 16384
        models[build_id] = _vision_model(
            str(meta["name"]),
            context=ctx,
            output=out,
            reasoning_effort=str(meta["reasoning_effort"]),
        )

    provider: dict[str, Any] = {
        "chiron": {
            "name": "ChironAI",
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": base_url.rstrip("/"),
                "apiKey": api_key,
            },
            "models": models,
        }
    }
    if hermes_api_key:
        hermes_models = {
            model_id: _vision_model(str(meta["name"]), context=int(meta["context"]))
            for model_id, meta in HERMES_OPENCODE_MODELS.items()
        }
        provider["hermes"] = {
            "name": "Hermes",
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": (hermes_base_url or _default_hermes_base_url()).rstrip("/"),
                "apiKey": hermes_api_key,
            },
            "models": hermes_models,
        }

    return {
        "$schema": "https://opencode.ai/config.json",
        "disabled_providers": [],
        "model": "chiron/Hard-worker-2",
        "provider": provider,
    }


def load_proxy_settings(db_path: Path) -> tuple[list[dict[str, Any]], str]:
    if not db_path.is_file():
        raise SystemExit(f"webui database not found: {db_path}")

    con = sqlite3.connect(db_path)
    try:
        builds_raw = con.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("llm_proxy_builds",),
        ).fetchone()
        key_raw = con.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("llm_proxy_api_key",),
        ).fetchone()
    finally:
        con.close()

    if not builds_raw or not key_raw:
        raise SystemExit("missing builds or api key in webui.db")

    builds = json.loads(builds_raw[0])
    if not isinstance(builds, list):
        raise SystemExit("llm_proxy_builds must be a JSON array")

    api_key = str(json.loads(key_raw[0]).get("secret") or "").strip()
    if not api_key:
        raise SystemExit("proxy api key secret missing")

    return builds, api_key


def write_opencode_config(config: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    if output_path.suffix == ".jsonc":
        sibling = output_path.with_suffix(".json")
        sibling.write_text(payload, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an OpenCode config with ChironAI vision-capable build models. "
            "Reads proxy builds and API key from the WebUI SQLite database."
        ),
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help=(
            "Path to webui.db (default: WEBUI_DB_PATH env var, else <repo>/logs/webui.db)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output opencode.jsonc path (default: ~/.config/opencode/opencode.jsonc)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Chiron /v1 base URL for OpenCode (default: http://127.0.0.1:8080/v1)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    db_path = args.db_path or _default_db_path()
    output_path = args.output or _default_output_path()
    base_url = (args.base_url or _default_base_url()).strip()

    builds, api_key = load_proxy_settings(db_path)
    hermes_key = _load_hermes_api_key()
    config = build_opencode_config(
        builds=builds,
        api_key=api_key,
        base_url=base_url,
        hermes_api_key=hermes_key,
        hermes_base_url=_default_hermes_base_url(),
    )
    write_opencode_config(config, output_path)

    names: list[str] = []
    for provider in config["provider"].values():
        names.extend(sorted(provider.get("models") or {}))
    print(f"wrote {output_path}")
    print("models:", ", ".join(names))


if __name__ == "__main__":
    main()
