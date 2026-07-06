"""Persisted custom OpenAI-compatible upstream LLM providers."""

from __future__ import annotations

import json
import re
from typing import Any

CUSTOM_OPENAI_PROVIDERS_APP_KEY = "custom_openai_providers"
_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}[a-z0-9]$")
_RESERVED_PROVIDER_IDS = frozenset({"ollama"})


def _normalize_base_url(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        raise ValueError("base_url is required")
    if not value.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    return value


def validate_provider_id(provider_id: str) -> str:
    value = str(provider_id or "").strip().lower()
    if not value or not _PROVIDER_ID_RE.match(value):
        raise ValueError(
            "id must be 2-64 chars, lowercase letters, digits, hyphens, underscores; start with a letter"
        )
    if value in _RESERVED_PROVIDER_IDS:
        raise ValueError(f"id {value!r} is reserved")
    return value


def _mask_api_key(secret: str) -> str:
    value = str(secret or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    secret = str(record.get("api_key") or "").strip()
    return {
        "id": str(record.get("id") or ""),
        "display_name": str(record.get("display_name") or record.get("id") or ""),
        "base_url": str(record.get("base_url") or ""),
        "enabled": bool(record.get("enabled", True)),
        "default_headers": dict(record.get("default_headers") or {}),
        "organization": str(record.get("organization") or ""),
        "manual_models": [str(m) for m in (record.get("manual_models") or []) if str(m).strip()],
        "api_key_configured": bool(secret),
        "api_key_masked": _mask_api_key(secret) if secret else None,
        "kind": "openai_compatible",
    }


def load_custom_openai_provider_records(settings_repo: Any) -> list[dict[str, Any]]:
    raw = settings_repo.get_app_setting(CUSTOM_OPENAI_PROVIDERS_APP_KEY)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            out.append(dict(item))
    return out


def save_custom_openai_provider_records(settings_repo: Any, records: list[dict[str, Any]]) -> None:
    settings_repo.set_app_setting(
        CUSTOM_OPENAI_PROVIDERS_APP_KEY,
        json.dumps(records, separators=(",", ":")),
    )


def list_custom_openai_providers_public(settings_repo: Any) -> list[dict[str, Any]]:
    return [_public_record(record) for record in load_custom_openai_provider_records(settings_repo)]


def get_custom_openai_provider_record(settings_repo: Any, provider_id: str) -> dict[str, Any] | None:
    pid = validate_provider_id(provider_id)
    for record in load_custom_openai_provider_records(settings_repo):
        if str(record.get("id") or "").strip().lower() == pid:
            return dict(record)
    return None


def get_custom_openai_provider_secret(settings_repo: Any, provider_id: str) -> dict[str, Any] | None:
    record = get_custom_openai_provider_record(settings_repo, provider_id)
    if record is None or not record.get("enabled", True):
        return None
    secret = str(record.get("api_key") or "").strip()
    if not secret:
        return None
    return record


def upsert_custom_openai_provider(
    settings_repo: Any,
    *,
    provider_id: str,
    display_name: str,
    base_url: str,
    api_key: str | None = None,
    default_headers: dict[str, Any] | None = None,
    organization: str | None = None,
    manual_models: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    pid = validate_provider_id(provider_id)
    normalized_url = _normalize_base_url(base_url)
    records = load_custom_openai_provider_records(settings_repo)
    existing = next((r for r in records if str(r.get("id") or "").strip().lower() == pid), None)
    secret = str(api_key or "").strip()
    if existing is None and not secret:
        raise ValueError("api_key is required when creating a provider")
    if existing is not None and not secret:
        secret = str(existing.get("api_key") or "").strip()
    next_record = {
        "id": pid,
        "display_name": str(display_name or pid).strip() or pid,
        "base_url": normalized_url,
        "api_key": secret,
        "default_headers": dict(default_headers or (existing or {}).get("default_headers") or {}),
        "organization": str(organization or (existing or {}).get("organization") or "").strip(),
        "manual_models": [str(m).strip() for m in (manual_models if manual_models is not None else (existing or {}).get("manual_models") or []) if str(m).strip()],
        "enabled": bool(enabled),
        "kind": "openai_compatible",
    }
    if existing is None:
        records.append(next_record)
    else:
        records = [next_record if str(r.get("id") or "").strip().lower() == pid else r for r in records]
    save_custom_openai_provider_records(settings_repo, records)
    return _public_record(next_record)


def delete_custom_openai_provider(settings_repo: Any, provider_id: str) -> bool:
    pid = validate_provider_id(provider_id)
    records = load_custom_openai_provider_records(settings_repo)
    kept = [r for r in records if str(r.get("id") or "").strip().lower() != pid]
    if len(kept) == len(records):
        return False
    save_custom_openai_provider_records(settings_repo, kept)
    return True
