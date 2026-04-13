"""
WebUI JSON API for ClawCode: status, traces, vendor sync, rollback-previous.

Safe to import when ClawCode is not on sys.path — routes return available=false.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLAWCODE_SRC = _REPO_ROOT / "CoreModules" / "ClawCode"
_VENDOR_NESTED_GIT_MIGRATED = False


def _ensure_chironai_rag_path() -> None:
    p = _REPO_ROOT / "CoreModules" / "RagService"
    if p.is_dir():
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure_chironai_rag_path()
try:
    from chironai_rag.bindings import ConsumerRagBindings
    from chironai_rag.consumers import CLAWCODE_RAG_COLLECTION_APP_SETTING, RagConsumer

    _CHIRONAI_RAG_BINDINGS = True
except ImportError:
    ConsumerRagBindings = None  # type: ignore[misc, assignment]
    RagConsumer = None  # type: ignore[misc, assignment]
    CLAWCODE_RAG_COLLECTION_APP_SETTING = "clawcode_rag_collection"
    _CHIRONAI_RAG_BINDINGS = False


def _ensure_clawcode_path() -> bool:
    s = str(_CLAWCODE_SRC)
    if s not in sys.path:
        sys.path.insert(0, s)
    try:
        import clawcode.trace_store  # noqa: F401

        return True
    except ImportError:
        return False


clawcode_bp = Blueprint("clawcode_webui", __name__, url_prefix="/api/webui/clawcode")


@clawcode_bp.get("/status")
def clawcode_status():
    if not _CLAWCODE_SRC.is_dir():
        return jsonify({"available": False, "reason": "CoreModules/ClawCode missing"})
    if not _ensure_clawcode_path():
        return jsonify({"available": False, "reason": "clawcode package import failed"})

    try:
        from config import (
            get_ollama_chat_model,
            get_clawcode_enabled,
            get_clawcode_host,
            get_clawcode_mcp_http_enabled,
            get_clawcode_mcp_port,
            get_clawcode_openai_port,
            get_clawcode_vendor_config,
            get_qdrant_collection_name,
            get_server_host,
        )
        from infrastructure.database import get_settings_repository
        from clawcode.vendor_manager import (
            migrate_inactive_versions_to_backups,
            migrate_strip_nested_git_all_versions,
            read_active,
        )

        vc = get_clawcode_vendor_config()
        global _VENDOR_NESTED_GIT_MIGRATED
        if not _VENDOR_NESTED_GIT_MIGRATED:
            migrate_strip_nested_git_all_versions(_REPO_ROOT, vc["root_relative"])
            _VENDOR_NESTED_GIT_MIGRATED = True
        migrate_inactive_versions_to_backups(_REPO_ROOT / vc["root_relative"])
        settings_repo = get_settings_repository()
        config_chat_model = get_ollama_chat_model()
        stored_rag = (settings_repo.get_app_setting(CLAWCODE_RAG_COLLECTION_APP_SETTING) or "").strip()
        config_rag = get_qdrant_collection_name()
        effective_rag = stored_rag or config_rag
        root_rel = vc["root_relative"]
        active = read_active(_REPO_ROOT / root_rel)
        host = get_clawcode_host()
        if host == "0.0.0.0":
            display_host = get_server_host()
            if display_host == "0.0.0.0":
                display_host = "127.0.0.1"
        else:
            display_host = host
        return jsonify(
            {
                "available": True,
                "enabled": get_clawcode_enabled(),
                "openai_port": get_clawcode_openai_port(),
                "mcp_port": get_clawcode_mcp_port(),
                "mcp_http_enabled": get_clawcode_mcp_http_enabled(),
                "host": host,
                "display_host": display_host,
                "config_chat_model": config_chat_model,
                "rag_collection": effective_rag,
                "stored_rag_collection": stored_rag,
                "config_default_rag_collection": config_rag,
                "openai_base_url": f"http://{display_host}:{get_clawcode_openai_port()}",
                "mcp_info_url": f"http://{display_host}:{get_clawcode_mcp_port()}/info",
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


def _annotate_claw_trace_row(rec: dict) -> dict:
    """Copy trace dict and mark optimistic queue pulses (not final outcomes, not journal-persisted)."""
    out = dict(rec)
    out["is_optimistic_pulse"] = bool(rec.get("journal_skip"))
    return out


@clawcode_bp.get("/traces")
def clawcode_traces():
    if not _ensure_clawcode_path():
        return jsonify({"traces": [], "available": False})
    try:
        lim_raw = request.args.get("limit", "40")
        limit = max(1, min(200, int(lim_raw)))
    except (TypeError, ValueError):
        limit = 40
    from clawcode.trace_store import recent

    rows = list(reversed(recent(limit)))
    omit_pulse = (request.args.get("omit_pulse") or "").strip().lower() in ("1", "true", "yes", "on")
    if omit_pulse:
        rows = [r for r in rows if isinstance(r, dict) and not r.get("journal_skip")]
    return jsonify({"available": True, "traces": [_annotate_claw_trace_row(r) if isinstance(r, dict) else r for r in rows]})


@clawcode_bp.post("/traces/clear")
def clawcode_traces_clear():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False}), 400
    from clawcode.trace_store import clear

    clear()
    return jsonify({"ok": True})


@clawcode_bp.get("/journal")
def clawcode_journal_get():
    """Persisted ClawCode traces from SQLite (session_id=clawcode)."""
    try:
        lim_raw = request.args.get("limit", "200")
        limit = max(1, min(5000, int(lim_raw)))
    except (TypeError, ValueError):
        limit = 200
    since_id = request.args.get("since_id")
    from_date = (request.args.get("from") or "").strip() or None
    to_date = (request.args.get("to") or "").strip() or None
    try:
        from infrastructure.database import get_logs_repository

        logs_repo = get_logs_repository()
        logs = logs_repo.get_logs(
            session_id="clawcode",
            level="INFO",
            limit=limit,
            since_id=int(since_id) if since_id else None,
            source="clawcode",
            include_system=False,
            from_date=from_date,
            to_date=to_date,
        )
        return jsonify({"ok": True, "logs": logs})
    except Exception as e:
        return jsonify({"ok": False, "logs": [], "error": str(e)}), 500


@clawcode_bp.delete("/journal")
def clawcode_journal_delete():
    """Delete persisted ClawCode journal rows (does not clear in-memory trace buffer)."""
    try:
        from infrastructure.database import get_logs_repository

        deleted = get_logs_repository().delete_clawcode_logs()
        return jsonify({"ok": True, "deleted_count": deleted})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.get("/vendor/main-sha")
def clawcode_vendor_main_sha():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    try:
        from config import get_clawcode_vendor_config

        from clawcode.vendor_manager import fetch_main_sha

        vc = get_clawcode_vendor_config()
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("CLAWCODE_GITHUB_TOKEN")
        sha = fetch_main_sha(vc["github_owner"], vc["github_repo"], token=token)
        if not sha:
            return jsonify({"ok": False, "error": "GitHub API did not return sha"}), 502
        return jsonify({"ok": True, "sha": sha, "full_sha": sha if len(sha) >= 40 else None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.get("/vendor/versions")
def clawcode_vendor_versions():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "versions": []}), 400
    from config import get_clawcode_vendor_config

    from clawcode.vendor_manager import (
        can_rollback,
        list_version_entries,
        migrate_inactive_versions_to_backups,
        read_active,
        vendor_root,
    )

    vc = get_clawcode_vendor_config()
    root = vendor_root(_REPO_ROOT, vc["root_relative"])
    migrate_inactive_versions_to_backups(root)
    return jsonify(
        {
            "ok": True,
            "versions": list_version_entries(root),
            "active": read_active(root),
            "can_rollback": can_rollback(root),
        }
    )


@clawcode_bp.post("/vendor/sync")
def clawcode_vendor_sync():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    from config import get_clawcode_vendor_config

    from clawcode.vendor_manager import sync_latest

    vc = get_clawcode_vendor_config()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("CLAWCODE_GITHUB_TOKEN")
    out = sync_latest(
        _REPO_ROOT,
        vc["github_owner"],
        vc["github_repo"],
        vc["root_relative"],
        token=token,
    )
    code = 200 if out.get("ok") else 502
    return jsonify(out), code


@clawcode_bp.post("/vendor/rollback-previous")
def clawcode_vendor_rollback_previous():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    from config import get_clawcode_vendor_config

    from clawcode.vendor_manager import rollback_to_previous

    vc = get_clawcode_vendor_config()
    out = rollback_to_previous(_REPO_ROOT, vc["root_relative"])
    code = 200 if out.get("ok") else 400
    return jsonify(out), code


@clawcode_bp.post("/vendor/rollback")
def clawcode_vendor_rollback_sha():
    """Body: {\"sha\": \"40-char hex\"} — activate that installed vendor tree."""
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    sha = body.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        return jsonify({"ok": False, "error": "missing sha"}), 400
    from config import get_clawcode_vendor_config

    from clawcode.vendor_manager import rollback_to_sha

    vc = get_clawcode_vendor_config()
    out = rollback_to_sha(_REPO_ROOT, vc["root_relative"], sha.strip())
    code = 200 if out.get("ok") else 400
    return jsonify(out), code


@clawcode_bp.get("/settings")
def clawcode_get_settings():
    """
    Return ClawCode-specific settings: RAG collection binding.

    Model and agent runtime for proxy traffic are configured via LLM Proxy builds (backend claw).
    ``merge_client_tools`` is set in ``config/clawcode.yaml`` or env ``CLAWCODE_MERGE_CLIENT_TOOLS``.
    """
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    try:
        from config import (
            get_clawcode_max_agent_steps,
            get_clawcode_max_agent_steps_config_yaml,
            get_qdrant_collection_name,
        )
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        stored_rag = (repo.get_app_setting(CLAWCODE_RAG_COLLECTION_APP_SETTING) or "").strip()
        config_rag = get_qdrant_collection_name()
        effective_rag = stored_rag or config_rag

        return jsonify(
            {
                "ok": True,
                "rag_collection": effective_rag,
                "stored_rag_collection": stored_rag,
                "config_default_rag_collection": config_rag,
                "max_agent_steps": get_clawcode_max_agent_steps(),
                "config_max_agent_steps_yaml": get_clawcode_max_agent_steps_config_yaml(),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/settings")
def clawcode_update_settings():
    """
    Persist ClawCode settings.

    Body may include: rag_collection.
    """
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    allowed = ("rag_collection",)
    if not any(k in body for k in allowed):
        return jsonify(
            {"ok": False, "error": f"Provide one or more of: {', '.join(allowed)}"}
        ), 400
    try:
        from infrastructure.database import get_settings_repository

        repo = get_settings_repository()
        out: dict[str, Any] = {"ok": True}
        if "rag_collection" in body:
            raw = body.get("rag_collection")
            rag_coll = str(raw).strip() if raw is not None else ""
            if _CHIRONAI_RAG_BINDINGS and ConsumerRagBindings is not None and RagConsumer is not None:
                ConsumerRagBindings(repo).set_stored_collection(RagConsumer.CLAWCODE, rag_coll)
            else:
                repo.set_app_setting(CLAWCODE_RAG_COLLECTION_APP_SETTING, rag_coll)
            out["rag_collection"] = rag_coll

        return jsonify(out)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.get("/skills")
def clawcode_skills_list():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_registry import (
            enabled_skill_ids_for_registry,
            load_skill_policy,
            load_skills_registry,
        )

        repo = get_settings_repository()
        policy = load_skill_policy(repo)
        registry = load_skills_registry(repo)
        enabled_set = set(enabled_skill_ids_for_registry(registry, policy))
        skills = []
        for rec in sorted(registry.values(), key=lambda r: (r.invocation_name or "", r.id)):
            sid = rec.id
            skills.append(
                {
                    **rec.to_json(),
                    "enabled": sid in enabled_set,
                }
            )
        return jsonify({"ok": True, "skills": skills})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "skills": []}), 500


_MAX_SKILL_MD_BYTES = 512_000


@clawcode_bp.get("/skills/skill-md")
def clawcode_skills_skill_md():
    """Read-only SKILL.md for Model Tester / debug (by skill_id or invocation query)."""
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    skill_id = (request.args.get("skill_id") or "").strip()
    invocation = (request.args.get("invocation") or "").strip()
    if not skill_id and not invocation:
        return jsonify({"ok": False, "error": "skill_id or invocation is required"}), 400
    try:
        from infrastructure.database import get_settings_repository

        from clawcode.skills_registry import load_skills_registry

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        rec = None
        if skill_id and skill_id in registry:
            rec = registry[skill_id]
        elif invocation:
            inv_l = invocation.lower()
            for r in registry.values():
                if (r.invocation_name or "").strip().lower() == inv_l or r.id == invocation:
                    rec = r
                    break
        if rec is None:
            return jsonify({"ok": False, "error": "skill not found"}), 404
        skill_path = Path(str(rec.installed_path)) / "SKILL.md"
        if not skill_path.is_file():
            return jsonify({"ok": False, "error": "SKILL.md missing"}), 404
        raw = skill_path.read_bytes()
        truncated = len(raw) > _MAX_SKILL_MD_BYTES
        if truncated:
            raw = raw[:_MAX_SKILL_MD_BYTES]
        content = raw.decode("utf-8", errors="replace")
        return jsonify(
            {
                "ok": True,
                "skill_id": rec.id,
                "invocation_name": rec.invocation_name,
                "content": content,
                "truncated": truncated,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/install")
def clawcode_skills_install():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_manager import install_skills_from_git
        from clawcode.skills_registry import load_skills_registry, store_skills_registry

        repo = get_settings_repository()
        url = (body.get("url") or "").strip()
        ref = (body.get("ref") or "").strip() or None
        subdir = (body.get("subdir") or "").strip() or None
        if not url:
            return jsonify({"ok": False, "error": "url is required"}), 400
        installed = install_skills_from_git(url=url, ref=ref, subdir=subdir)
        registry = load_skills_registry(repo)
        for rec in installed:
            registry[rec.id] = rec
        store_skills_registry(repo, registry)
        return jsonify(
            {
                "ok": True,
                "installed_count": len(installed),
                "installed": [r.to_json() for r in installed],
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/update")
def clawcode_skills_update():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    skill_id = (body.get("skill_id") or "").strip()
    if not skill_id:
        return jsonify({"ok": False, "error": "skill_id is required"}), 400
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_manager import SkillRecord, update_skill_from_source
        from clawcode.skills_registry import load_skills_registry, store_skills_registry

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        rec = registry.get(skill_id)
        if not rec:
            return jsonify({"ok": False, "error": f"skill not found: {skill_id}"}), 404
        if not isinstance(rec, SkillRecord):
            return jsonify({"ok": False, "error": "invalid skill record"}), 400
        updated = update_skill_from_source(rec)
        registry[updated.id] = updated
        store_skills_registry(repo, registry)
        return jsonify({"ok": True, "skill": updated.to_json()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/remote-heads")
def clawcode_skills_remote_heads():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable", "heads": []}), 400
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_manager import resolve_remote_head_sha
        from clawcode.skills_registry import load_skills_registry

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        seen: set[tuple[str, str | None]] = set()
        pairs: list[tuple[str, str | None]] = []
        for rec in registry.values():
            src = rec.source
            if src.type != "git" or not src.url:
                continue
            url = src.url.strip()
            ref = src.ref.strip() if isinstance(src.ref, str) and src.ref.strip() else None
            key = (url, ref)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((url, ref))

        heads: list[dict[str, Any]] = []
        for url, ref in pairs:
            entry: dict[str, Any] = {"url": url, "ref": ref, "remote_sha": None, "error": None}
            try:
                entry["remote_sha"] = resolve_remote_head_sha(url, ref)
            except Exception as e:
                entry["error"] = str(e)
            heads.append(entry)
        return jsonify({"ok": True, "heads": heads})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "heads": []}), 500


@clawcode_bp.post("/skills/update-by-source")
def clawcode_skills_update_by_source():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url is required"}), 400
    ref = (body.get("ref") or "").strip() or None
    subdir = (body.get("subdir") or "").strip() or None
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_manager import update_skills_by_source
        from clawcode.skills_registry import load_skills_registry, store_skills_registry

        settings_repo = get_settings_repository()
        registry = load_skills_registry(settings_repo)
        updated = update_skills_by_source(url=url, ref=ref, subdir=subdir, registry=registry)
        if not updated:
            return jsonify({"ok": False, "error": "no skills match this source"}), 404
        for rec in updated:
            registry[rec.id] = rec
        store_skills_registry(settings_repo, registry)
        return jsonify(
            {
                "ok": True,
                "updated_count": len(updated),
                "skills": [r.to_json() for r in updated],
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/delete-by-source")
def clawcode_skills_delete_by_source():
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "url is required"}), 400
    ref = (body.get("ref") or "").strip() or None
    subdir = (body.get("subdir") or "").strip() or None
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_manager import delete_skills_by_source
        from clawcode.skills_registry import (
            load_skills_registry,
            remove_skill_from_policy_disabled,
            store_skills_registry,
        )

        settings_repo = get_settings_repository()
        registry = load_skills_registry(settings_repo)
        deleted_ids = delete_skills_by_source(url=url, ref=ref, subdir=subdir, registry=registry)
        if not deleted_ids:
            return jsonify({"ok": False, "error": "no skills match this source"}), 404
        store_skills_registry(settings_repo, registry)
        for sid in deleted_ids:
            remove_skill_from_policy_disabled(settings_repo, sid)
        return jsonify({"ok": True, "deleted_count": len(deleted_ids), "deleted": deleted_ids})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.delete("/skills/<skill_id>")
def clawcode_skills_delete(skill_id: str):
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    skill_id = (skill_id or "").strip()
    if not skill_id:
        return jsonify({"ok": False, "error": "skill_id is required"}), 400
    try:
        import shutil
        from pathlib import Path

        from infrastructure.database import get_settings_repository
        from clawcode.skills_registry import (
            load_skills_registry,
            remove_skill_from_policy_disabled,
            store_skills_registry,
        )

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        rec = registry.pop(skill_id, None)
        if rec is None:
            return jsonify({"ok": False, "error": f"skill not found: {skill_id}"}), 404
        try:
            p = Path(str(rec.installed_path))
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
        store_skills_registry(repo, registry)
        remove_skill_from_policy_disabled(repo, skill_id)
        return jsonify({"ok": True, "deleted": skill_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/<skill_id>/enable")
def clawcode_skills_enable(skill_id: str):
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    skill_id = (skill_id or "").strip()
    if not skill_id:
        return jsonify({"ok": False, "error": "skill_id is required"}), 400
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_registry import SkillPolicy, load_skill_policy, load_skills_registry, store_skill_policy

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        if skill_id not in registry:
            return jsonify({"ok": False, "error": f"skill not found: {skill_id}"}), 404
        policy = load_skill_policy(repo)
        nxt = [x for x in policy.disabled_skill_ids if x != skill_id]
        store_skill_policy(repo, SkillPolicy(disabled_skill_ids=nxt))
        return jsonify({"ok": True, "skill_id": skill_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@clawcode_bp.post("/skills/<skill_id>/disable")
def clawcode_skills_disable(skill_id: str):
    if not _ensure_clawcode_path():
        return jsonify({"ok": False, "error": "clawcode unavailable"}), 400
    skill_id = (skill_id or "").strip()
    if not skill_id:
        return jsonify({"ok": False, "error": "skill_id is required"}), 400
    try:
        from infrastructure.database import get_settings_repository
        from clawcode.skills_registry import SkillPolicy, load_skill_policy, load_skills_registry, store_skill_policy

        repo = get_settings_repository()
        registry = load_skills_registry(repo)
        if skill_id not in registry:
            return jsonify({"ok": False, "error": f"skill not found: {skill_id}"}), 404
        policy = load_skill_policy(repo)
        disabled = list(policy.disabled_skill_ids)
        if skill_id not in disabled:
            disabled.append(skill_id)
        store_skill_policy(repo, SkillPolicy(disabled_skill_ids=disabled))
        return jsonify({"ok": True, "skill_id": skill_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def register_clawcode_webui(app) -> None:
    """Register blueprint; no-op if blueprint import fails."""
    try:
        app.register_blueprint(clawcode_bp)
    except Exception:
        pass


__all__ = ["clawcode_bp", "register_clawcode_webui"]
