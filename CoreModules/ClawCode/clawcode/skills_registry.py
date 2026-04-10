from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from infrastructure.database.settings_repository import SettingsRepository

from clawcode.skills_manager import SkillRecord


SKILLS_REGISTRY_KEY = "clawcode_skills_registry_v1"
SKILLS_POLICY_KEY = "clawcode_skills_policy_v1"

_MODEL_KEY_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


@dataclass(frozen=True)
class SkillPolicy:
    """Global policy: installed skills are on for every model unless listed here."""

    disabled_skill_ids: list[str]

    def to_json(self) -> dict[str, Any]:
        return {"disabled_skill_ids": list(self.disabled_skill_ids)}

    @staticmethod
    def from_json(obj: object) -> "SkillPolicy":
        if not isinstance(obj, dict):
            return SkillPolicy(disabled_skill_ids=[])
        raw = obj.get("disabled_skill_ids")
        disabled: list[str] = []
        if isinstance(raw, list):
            for x in raw:
                if isinstance(x, str) and x.strip():
                    disabled.append(x.strip())
        return SkillPolicy(disabled_skill_ids=disabled)


def load_skill_policy(repo: SettingsRepository) -> SkillPolicy:
    raw = (repo.get_app_setting(SKILLS_POLICY_KEY) or "").strip()
    if not raw:
        return SkillPolicy(disabled_skill_ids=[])
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return SkillPolicy(disabled_skill_ids=[])
    return SkillPolicy.from_json(obj)


def store_skill_policy(repo: SettingsRepository, policy: SkillPolicy) -> None:
    repo.set_app_setting(SKILLS_POLICY_KEY, json.dumps(policy.to_json(), ensure_ascii=False))


def load_skills_registry(repo: SettingsRepository) -> dict[str, SkillRecord]:
    raw = (repo.get_app_setting(SKILLS_REGISTRY_KEY) or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, SkillRecord] = {}
    for skill_id, rec in obj.items():
        if not isinstance(skill_id, str) or not skill_id.strip():
            continue
        parsed = SkillRecord.from_json(rec)
        if not parsed or not parsed.id:
            continue
        out[parsed.id] = parsed
    return out


def store_skills_registry(repo: SettingsRepository, records: dict[str, SkillRecord]) -> None:
    payload = {k: v.to_json() for k, v in records.items() if isinstance(k, str) and v}
    repo.set_app_setting(SKILLS_REGISTRY_KEY, json.dumps(payload, ensure_ascii=False))


def enabled_skill_ids_for_registry(
    registry: dict[str, SkillRecord], policy: SkillPolicy
) -> list[str]:
    disabled = {x for x in policy.disabled_skill_ids if isinstance(x, str) and x.strip()}
    return sorted((sid for sid in registry if sid not in disabled), key=lambda s: (registry[s].invocation_name or "", s))


def remove_skill_from_policy_disabled(repo: SettingsRepository, skill_id: str) -> None:
    policy = load_skill_policy(repo)
    sid = (skill_id or "").strip()
    if not sid:
        return
    nxt = [x for x in policy.disabled_skill_ids if x != sid]
    if len(nxt) == len(policy.disabled_skill_ids):
        return
    store_skill_policy(repo, SkillPolicy(disabled_skill_ids=nxt))
