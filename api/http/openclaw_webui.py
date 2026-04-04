"""
WebUI JSON API for OpenClaw: status, traces, vendor sync/rollback.

Safe to import when OpenClaw is not on sys.path — routes return available=false.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENCLAW_SRC = _REPO_ROOT / "CoreModules" / "OpenClaw"
_VENDOR_NESTED_GIT_MIGRATED = False


def _ensure_openclaw_path() -> bool:
    s = str(_OPENCLAW_SRC)
    if s not in sys.path:
        sys.path.insert(0, s)
    try:
        import openclaw.trace_store  # noqa: F401

        return True
    except ImportError:
        return False


openclaw_bp = Blueprint("openclaw_webui", __name__, url_prefix="/api/webui/openclaw")


@openclaw_bp.get("/status")
def openclaw_status():
    if not _OPENCLAW_SRC.is_dir():
        return jsonify({"available": False, "reason": "CoreModules/OpenClaw missing"})
    if not _ensure_openclaw_path():
        return jsonify({"available": False, "reason": "openclaw package import failed"})

    try:
        from config import (
            get_ollama_chat_model,
            get_openclaw_enabled,
            get_openclaw_host,
            get_openclaw_logical_model_id,
            get_openclaw_mcp_http_enabled,
            get_openclaw_mcp_port,
            get_openclaw_openai_port,
            get_openclaw_vendor_config,
            get_qdrant_collection_name,
            get_server_host,
        )
        from infrastructure.database import get_settings_repository
        from openclaw.vendor_manager import migrate_strip_nested_git_all_versions, read_active

        vc = get_openclaw_vendor_config()
        global _VENDOR_NESTED_GIT_MIGRATED
        if not _VENDOR_NESTED_GIT_MIGRATED:
            migrate_strip_nested_git_all_versions(_REPO_ROOT, vc["root_relative"])
            _VENDOR_NESTED_GIT_MIGRATED = True
        settings_repo = get_settings_repository()
        stored_default = (settings_repo.get_app_setting("openclaw_default_model") or "").strip()
        effective_default = stored_default or get_ollama_chat_model()
        stored_rag = (settings_repo.get_app_setting("openclaw_rag_collection") or "").strip()
        config_rag = get_qdrant_collection_name()
        effective_rag = stored_rag or config_rag
        root_rel = vc["root_relative"]
        active = read_active(_REPO_ROOT / root_rel)
        host = get_openclaw_host()
        if host == "0.0.0.0":
            display_host = get_server_host()
            if display_host == "0.0.0.0":
                display_host = "127.0.0.1"
        else:
            display_host = host
        return jsonify(
            {
                "available": True,
                "enabled": get_openclaw_enabled(),
                "openai_port": get_openclaw_openai_port(),
                "mcp_port": get_openclaw_mcp_port(),
                "mcp_http_enabled": get_openclaw_mcp_http_enabled(),
                "host": host,
                "display_host": display_host,
                "logical_model_id": get_openclaw_logical_model_id(),
                "default_ollama_model": effective_default,
                "rag_collection": effective_rag,
                "stored_rag_collection": stored_rag,
                "config_default_rag_collection": config_rag,
                "openai_base_url": f"http://{display_host}:{get_openclaw_openai_port()}",
                "mcp_info_url": f"http://{display_host}:{get_openclaw_mcp_port()}/info",
                "vendor": {
                    "github_owner": vc["github_owner"],
                    "github_repo": vc["github_repo"],
                    "branch": vc["branch"],
                    "root_relative": root_rel,
                    "active": active,
                },
            }
        )
    except Exception as e:
        return jsonify({"available": False, "reason": str(e)}), 200


@openclaw_bp.get("/traces")
def openclaw_traces():
    if not _ensure_openclaw_path():
        return jsonify({"traces": [], "available": False})
    try:
        lim_raw = request.args.get("limit", "40")
        limit = max(1, min(200, int(lim_raw)))
    except (TypeError, ValueError):
        limit = 40
    from openclaw.trace_store import recent

    return jsonify({"available": True, "traces": list(reversed(recent(limit)))})


@openclaw_bp.post("/traces/clear")
def openclaw_traces_clear():
    if not _ensure_openclaw_path():
        return jsonify({"ok": False}), 400
    from openclaw.trace_store import clear

    clear()
    return jsonify({"ok": True})


@openclaw_bp.get("/vendor/main-sha")
def openclaw_vendor_main_sha():
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "error": "openclaw unavailable"}), 400
    try:
        from config import get_openclaw_vendor_config

        from openclaw.vendor_manager import fetch_main_sha

        vc = get_openclaw_vendor_config()
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENCLAW_GITHUB_TOKEN")
        sha = fetch_main_sha(vc["github_owner"], vc["github_repo"], token=token)
        if not sha:
            return jsonify({"ok": False, "error": "GitHub API did not return sha"}), 502
        return jsonify({"ok": True, "sha": sha, "full_sha": sha if len(sha) >= 40 else None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@openclaw_bp.get("/vendor/versions")
def openclaw_vendor_versions():
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "versions": []}), 400
    from config import get_openclaw_vendor_config

    from openclaw.vendor_manager import list_version_shas, read_active, vendor_root

    vc = get_openclaw_vendor_config()
    root = vendor_root(_REPO_ROOT, vc["root_relative"])
    return jsonify(
        {
            "ok": True,
            "versions": list_version_shas(root),
            "active": read_active(root),
        }
    )


@openclaw_bp.post("/vendor/sync")
def openclaw_vendor_sync():
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "error": "openclaw unavailable"}), 400
    from config import get_openclaw_vendor_config

    from openclaw.vendor_manager import sync_latest

    vc = get_openclaw_vendor_config()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENCLAW_GITHUB_TOKEN")
    out = sync_latest(
        _REPO_ROOT,
        vc["github_owner"],
        vc["github_repo"],
        vc["root_relative"],
        token=token,
    )
    code = 200 if out.get("ok") else 502
    return jsonify(out), code


@openclaw_bp.post("/vendor/rollback")
def openclaw_vendor_rollback():
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "error": "openclaw unavailable"}), 400
    body = request.get_json(silent=True) or {}
    sha = (body.get("sha") or "").strip().lower()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        return jsonify({"ok": False, "error": "full 40-char sha required"}), 400
    from config import get_openclaw_vendor_config

    from openclaw.vendor_manager import rollback

    vc = get_openclaw_vendor_config()
    out = rollback(_REPO_ROOT, sha, vc["root_relative"])
    code = 200 if out.get("ok") else 400
    return jsonify(out), code


@openclaw_bp.get("/settings")
def openclaw_get_settings():
    """
    Return OpenClaw-specific settings (default model) and available Ollama models.

    This is separate from LlmProxy model-settings to keep concerns isolated.
    """
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "error": "openclaw unavailable"}), 400
    try:
        from config import (
            get_ollama_base_url,
            get_ollama_chat_model,
            get_ollama_chat_options,
            get_openclaw_max_agent_steps,
            get_openclaw_max_agent_steps_config_yaml,
            get_qdrant_collection_name,
        )
        from infrastructure.database import get_settings_repository
        from infrastructure.ollama.cli_runner import invoke_tags

        repo = get_settings_repository()
        stored_default = (repo.get_app_setting("openclaw_default_model") or "").strip()
        fallback = get_ollama_chat_model()
        effective_default = stored_default or fallback
        stored_rag = (repo.get_app_setting("openclaw_rag_collection") or "").strip()
        config_rag = get_qdrant_collection_name()
        effective_rag = stored_rag or config_rag

        stored_max_steps = (repo.get_app_setting("openclaw_max_agent_steps") or "").strip()
        stored_temp = (repo.get_app_setting("openclaw_chat_temperature") or "").strip()
        stored_top_p = (repo.get_app_setting("openclaw_chat_top_p") or "").strip()
        global_opts = get_ollama_chat_options() or {}

        base_url = get_ollama_base_url()
        tags = invoke_tags(base_url=base_url, timeout=5.0)
        models = []
        for m in tags.get("models") or []:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or m.get("model") or "").strip()
            if not name:
                continue
            models.append({"id": name, "name": name})

        if fallback and all(fallback != mm["id"] for mm in models):
            models.insert(0, {"id": fallback, "name": fallback})

        return jsonify(
            {
                "ok": True,
                "default_model": effective_default,
                "stored_default_model": stored_default,
                "available_models": models,
                "rag_collection": effective_rag,
                "stored_rag_collection": stored_rag,
                "config_default_rag_collection": config_rag,
                "max_agent_steps": get_openclaw_max_agent_steps(),
                "stored_max_agent_steps": stored_max_steps,
                "config_max_agent_steps_yaml": get_openclaw_max_agent_steps_config_yaml(),
                "stored_chat_temperature": stored_temp,
                "stored_chat_top_p": stored_top_p,
                "global_chat_temperature": global_opts.get("temperature"),
                "global_chat_top_p": global_opts.get("top_p"),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _clearable_str(body: dict[str, Any], key: str) -> str | None:
    """If key missing, None. If null, ''. Else stringified strip."""
    if key not in body:
        return None
    v = body.get(key)
    if v is None:
        return ""
    return str(v).strip()


@openclaw_bp.post("/settings")
def openclaw_update_settings():
    """
    Persist OpenClaw settings.

    Body may include any of:
    - default_model, rag_collection, max_agent_steps, chat_temperature, chat_top_p
    Use null or empty string where supported to clear stored override.
    """
    if not _ensure_openclaw_path():
        return jsonify({"ok": False, "error": "openclaw unavailable"}), 400
    body = request.get_json(silent=True) or {}
    allowed = (
        "default_model",
        "rag_collection",
        "max_agent_steps",
        "chat_temperature",
        "chat_top_p",
    )
    if not any(k in body for k in allowed):
        return jsonify(
            {"ok": False, "error": f"Provide one or more of: {', '.join(allowed)}"}
        ), 400
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        out: dict[str, Any] = {"ok": True}
        if "default_model" in body:
            model = (body.get("default_model") or "").strip()
            if not model:
                return jsonify({"ok": False, "error": "default_model cannot be empty"}), 400
            repo.set_app_setting("openclaw_default_model", model)
            out["default_model"] = model
        if "rag_collection" in body:
            raw = body.get("rag_collection")
            rag_coll = str(raw).strip() if raw is not None else ""
            repo.set_app_setting("openclaw_rag_collection", rag_coll)
            out["rag_collection"] = rag_coll

        ms = _clearable_str(body, "max_agent_steps")
        if ms is not None:
            if ms == "":
                repo.set_app_setting("openclaw_max_agent_steps", "")
                from config import get_openclaw_max_agent_steps

                out["max_agent_steps"] = get_openclaw_max_agent_steps()
            else:
                try:
                    n = int(ms)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "max_agent_steps must be an integer"}), 400
                if n < 1 or n > 256:
                    return jsonify(
                        {"ok": False, "error": "max_agent_steps must be between 1 and 256"}
                    ), 400
                repo.set_app_setting("openclaw_max_agent_steps", str(n))
                out["max_agent_steps"] = n

        ct = _clearable_str(body, "chat_temperature")
        if ct is not None:
            if ct == "":
                repo.set_app_setting("openclaw_chat_temperature", "")
                out["chat_temperature"] = ""
            else:
                try:
                    t = float(ct)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "chat_temperature must be a number"}), 400
                if t < 0 or t > 2:
                    return jsonify(
                        {"ok": False, "error": "chat_temperature must be between 0 and 2"}
                    ), 400
                repo.set_app_setting("openclaw_chat_temperature", ct)
                out["chat_temperature"] = ct

        tp = _clearable_str(body, "chat_top_p")
        if tp is not None:
            if tp == "":
                repo.set_app_setting("openclaw_chat_top_p", "")
                out["chat_top_p"] = ""
            else:
                try:
                    p = float(tp)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "chat_top_p must be a number"}), 400
                if p <= 0 or p > 1:
                    return jsonify({"ok": False, "error": "chat_top_p must be in (0, 1]"}), 400
                repo.set_app_setting("openclaw_chat_top_p", tp)
                out["chat_top_p"] = tp

        return jsonify(out)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def register_openclaw_webui(app) -> None:
    """Register blueprint; no-op if blueprint import fails."""
    try:
        app.register_blueprint(openclaw_bp)
    except Exception:
        pass


__all__ = ["openclaw_bp", "register_openclaw_webui"]
