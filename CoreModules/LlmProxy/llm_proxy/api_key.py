"""WebUI-managed API key helpers for the Chiron /v1 proxy."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any

LLM_PROXY_API_KEY_APP_SETTING = "llm_proxy_api_key"
LLM_PROXY_API_KEY_PREFIX = "chiron_sk_"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def hash_proxy_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def load_proxy_api_key_record(settings_repo: Any) -> dict[str, Any]:
    raw = settings_repo.get_app_setting(LLM_PROXY_API_KEY_APP_SETTING)
    if not raw:
        return {}
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(record, dict) or not str(record.get("sha256") or "").strip():
        return {}
    return record


def proxy_api_key_status(settings_repo: Any) -> dict[str, Any]:
    record = load_proxy_api_key_record(settings_repo)
    if not record:
        return {
            "configured": False,
            "prefix": None,
            "created_at": None,
            "rotated_at": None,
            "recoverable": False,
        }
    return {
        "configured": True,
        "prefix": str(record.get("prefix") or ""),
        "created_at": record.get("created_at"),
        "rotated_at": record.get("rotated_at"),
        "recoverable": bool(record.get("secret")),
    }


def generate_proxy_api_key_record(settings_repo: Any) -> tuple[str, dict[str, Any]]:
    existing = load_proxy_api_key_record(settings_repo)
    now = _now_iso()
    plaintext = f"{LLM_PROXY_API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    record = {
        "sha256": hash_proxy_api_key(plaintext),
        "secret": plaintext,
        "prefix": plaintext[:20],
        "created_at": existing.get("created_at") or now,
        "rotated_at": now if existing else None,
    }
    return plaintext, record


def reveal_proxy_api_key(settings_repo: Any) -> str:
    record = load_proxy_api_key_record(settings_repo)
    return str(record.get("secret") or "") if record else ""


def store_proxy_api_key_record(settings_repo: Any, record: dict[str, Any]) -> None:
    settings_repo.set_app_setting(LLM_PROXY_API_KEY_APP_SETTING, json.dumps(record, separators=(",", ":")))


def delete_proxy_api_key_record(settings_repo: Any) -> None:
    if hasattr(settings_repo, "delete_app_setting"):
        settings_repo.delete_app_setting(LLM_PROXY_API_KEY_APP_SETTING)
        return
    settings_repo.set_app_setting(LLM_PROXY_API_KEY_APP_SETTING, "")


def verify_proxy_api_key(settings_repo: Any, supplied_key: str) -> tuple[bool, bool]:
    record = load_proxy_api_key_record(settings_repo)
    if not record:
        return False, False
    expected_hash = str(record.get("sha256") or "")
    supplied_hash = hash_proxy_api_key(supplied_key)
    return True, hmac.compare_digest(supplied_hash, expected_hash)
