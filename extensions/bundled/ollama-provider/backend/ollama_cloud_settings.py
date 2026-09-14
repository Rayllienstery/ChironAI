"""
Ollama Cloud API key persistence, validation, and usage/quota reporting
for the ollama-provider extension.

Uses app_settings via an injected settings repository (same pattern as
model_visibility).  All ollama.com calls go to the public cloud API with a
Bearer key; nothing here talks to the local Ollama runtime.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_API_KEY_APP_KEY = "ollama_provider_ollama_api_key"
_CHECK_APP_KEY = "ollama_provider_cloud_api_key_check"

_CLOUD_TAGS_URL = "https://ollama.com/api/tags"
_CLOUD_USAGE_URL = "https://ollama.com/api/usage"
_CLOUD_ME_URL = "https://ollama.com/api/me"
_VALIDATE_TIMEOUT_SEC = 15.0
_USAGE_TIMEOUT_SEC = 10.0


def get_stored_api_key(settings_repo: Any) -> str:
    raw = settings_repo.get_app_setting(_API_KEY_APP_KEY)
    return str(raw or "").strip()


def save_api_key(settings_repo: Any, key: str) -> None:
    settings_repo.set_app_setting(_API_KEY_APP_KEY, (key or "").strip())


def get_check_record(settings_repo: Any) -> dict[str, Any]:
    raw = settings_repo.get_app_setting(_CHECK_APP_KEY)
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, dict) else {}


def set_check_record(settings_repo: Any, *, valid: bool | None, detail: str = "") -> None:
    payload = {"valid": valid, "detail": str(detail or "")[:500]}
    settings_repo.set_app_setting(_CHECK_APP_KEY, json.dumps(payload))


def mark_check_unknown_after_save(settings_repo: Any) -> None:
    set_check_record(settings_repo, valid=None, detail="")


def clear_api_key(settings_repo: Any) -> None:
    delete_fn = getattr(settings_repo, "delete_app_setting", None)
    if callable(delete_fn):
        delete_fn(_API_KEY_APP_KEY)
        delete_fn(_CHECK_APP_KEY)
        return
    settings_repo.set_app_setting(_API_KEY_APP_KEY, "")
    settings_repo.set_app_setting(_CHECK_APP_KEY, "{}")


def validate_cloud_api_key(key: str) -> tuple[bool, str]:
    trimmed = (key or "").strip()
    if not trimmed:
        return False, "API key is empty"
    req = urllib.request.Request(_CLOUD_TAGS_URL, method="GET")
    req.add_header("Authorization", f"Bearer {trimmed}")
    try:
        with urllib.request.urlopen(req, timeout=_VALIDATE_TIMEOUT_SEC) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status == 200:
                return True, "Cloud auth OK"
            return False, f"Unexpected HTTP {status}"
    except urllib.error.HTTPError as e:
        code = int(e.code or 0)
        if code in (401, 403):
            return False, "Invalid or revoked API key"
        return False, f"HTTP {code}: {e.reason or str(e)}"
    except urllib.error.URLError as e:
        return False, str(e.reason or e)
    except Exception as e:
        return False, str(e)


def cloud_auth_status_text(settings_repo: Any) -> str:
    key = get_stored_api_key(settings_repo)
    if not key:
        return "Not configured"
    rec = get_check_record(settings_repo)
    v = rec.get("valid")
    detail = str(rec.get("detail") or "").strip()
    if v is True:
        if detail and detail != "Cloud auth OK":
            return f"Valid — {detail}"
        return "Valid"
    if v is False:
        if detail:
            return f"Invalid — {detail}"
        return "Invalid"
    return "Saved (not verified)"


def _cloud_get_json(url: str, key: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _format_usage_fraction(usage: Any) -> str:
    try:
        value = float(usage)
    except (TypeError, ValueError):
        return "—"
    if value < 0:
        return "—"
    return f"{round(value * 100)}%"


def _summarize_usage_models(models: Any) -> str:
    if not isinstance(models, list) or not models:
        return ""
    parts: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        count = item.get("request_count")
        if not name or count is None:
            continue
        parts.append(f"{name}: {count}")
    return ", ".join(parts)


def fetch_cloud_usage(settings_repo: Any) -> dict[str, Any]:
    """Fetch ollama.com plan + quota usage for the stored API key.

    Returns a plain dict safe to embed in a tab payload:
    ``{configured, plan, session_usage, weekly_usage, session_models,
    weekly_models, activity_cost, error}``.  Never raises: network/auth
    failures come back as ``{"configured": ..., "error": ...}`` so the
    tab payload stays renderable.
    """
    key = get_stored_api_key(settings_repo)
    if not key:
        return {"configured": False}

    out: dict[str, Any] = {"configured": True}
    try:
        usage = _cloud_get_json(_CLOUD_USAGE_URL, key, _USAGE_TIMEOUT_SEC)
    except urllib.error.HTTPError as e:
        code = int(e.code or 0)
        if code in (401, 403):
            return {"configured": True, "error": "Invalid or revoked API key"}
        return {"configured": True, "error": f"HTTP {code}: {e.reason or str(e)}"}
    except Exception as e:
        return {"configured": True, "error": str(e)}

    limits = usage.get("limits") if isinstance(usage.get("limits"), dict) else {}
    session = limits.get("session") if isinstance(limits.get("session"), dict) else {}
    weekly = limits.get("weekly") if isinstance(limits.get("weekly"), dict) else {}
    activity = usage.get("activity") if isinstance(usage.get("activity"), dict) else {}

    out["session_usage"] = _format_usage_fraction(session.get("usage"))
    out["weekly_usage"] = _format_usage_fraction(weekly.get("usage"))
    out["session_models"] = _summarize_usage_models(session.get("models"))
    out["weekly_models"] = _summarize_usage_models(weekly.get("models"))
    cost = activity.get("cost")
    out["activity_cost"] = str(cost) if cost is not None else ""

    try:
        me = _cloud_get_json(_CLOUD_ME_URL, key, _USAGE_TIMEOUT_SEC)
        plan = str(me.get("Plan") or me.get("plan") or "").strip()
        if plan:
            out["plan"] = plan
    except Exception:
        # Plan is cosmetic; usage without it is still useful.
        pass
    return out


__all__ = [
    "clear_api_key",
    "cloud_auth_status_text",
    "fetch_cloud_usage",
    "get_check_record",
    "get_stored_api_key",
    "mark_check_unknown_after_save",
    "save_api_key",
    "set_check_record",
    "validate_cloud_api_key",
]