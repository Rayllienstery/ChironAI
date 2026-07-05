"""Update ~/.config/opencode/opencode.jsonc for ChironAI vision."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB = Path(r"c:\Users\Raylee\AI\logs\webui.db")
OUT = Path(r"c:\Users\Raylee\.config\opencode\opencode.jsonc")

VISION_MODEL_FIELDS: dict[str, Any] = {
    "attachment": True,
    "tool_call": True,
    "modalities": {
        "input": ["text", "image"],
        "output": ["text"],
    },
}


def _vision_model(name: str, *, context: int = 131072, output: int = 16384) -> dict[str, Any]:
    return {
        "name": name,
        **VISION_MODEL_FIELDS,
        "limit": {"context": context, "output": output},
    }


def main() -> None:
    con = sqlite3.connect(DB)
    builds_raw = con.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        ("llm_proxy_builds",),
    ).fetchone()
    key_raw = con.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        ("llm_proxy_api_key",),
    ).fetchone()
    if not builds_raw or not key_raw:
        raise SystemExit("missing builds or api key in webui.db")

    builds = json.loads(builds_raw[0])
    api_key = str(json.loads(key_raw[0]).get("secret") or "").strip()
    if not api_key:
        raise SystemExit("proxy api key secret missing")

    models: dict[str, Any] = {}
    for b in builds:
        build_id = str(b.get("id") or "").strip()
        if not build_id:
            continue
        try:
            ctx = int(b.get("num_ctx") or 131072)
        except (TypeError, ValueError):
            ctx = 131072
        try:
            out = int(b.get("num_predict") or 16384)
        except (TypeError, ValueError):
            out = 16384
        models[build_id] = _vision_model(build_id, context=ctx, output=out)

    config = {
        "$schema": "https://opencode.ai/config.json",
        "disabled_providers": [],
        "provider": {
            "chiron": {
                "name": "ChironAI",
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "baseURL": "http://127.0.0.1:8080/v1",
                    "apiKey": api_key,
                },
                "models": models,
            }
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print("models:", ", ".join(sorted(models)))


if __name__ == "__main__":
    main()
