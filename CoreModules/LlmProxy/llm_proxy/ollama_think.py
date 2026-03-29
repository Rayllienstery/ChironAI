"""Resolve Ollama native `think` flag from OpenAI-compatible / proxy request bodies."""

from __future__ import annotations

from typing import Any

# Keep local to avoid import path issues when CoreModules is used standalone.
REASONING_LEVEL_VALUES: tuple[str, ...] = ("low", "medium", "high")

_LEVEL_ALIASES = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "minimal": "low",
    "default": "medium",
    "reasoning": "medium",
}


def _normalize_level_str(raw: str) -> str | None:
    s = raw.strip().lower()
    if s in REASONING_LEVEL_VALUES:
        return s
    return _LEVEL_ALIASES.get(s)


def _parse_think_value(raw: Any) -> bool | str | None:
    """Normalize explicit `think` field from JSON (bool, str level, or string booleans)."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    if isinstance(raw, str):
        t = raw.strip().lower()
        if t in ("true", "1", "yes", "on"):
            return True
        if t in ("false", "0", "no", "off"):
            return False
        level = _normalize_level_str(raw)
        if level:
            return level
        if raw.strip():
            return raw.strip()
    return None


def _is_gpt_oss_model(model_name: str | None) -> bool:
    return "gpt-oss" in (model_name or "").lower()


def coerce_think_for_model(think: bool | str | None, model_name: str | None) -> bool | str | None:
    """
    GPT-OSS expects low/medium/high; booleans are ignored by Ollama for that family.
    Map bool True -> medium, bool False -> omit (None).
    """
    if think is None:
        return None
    if _is_gpt_oss_model(model_name):
        if isinstance(think, bool):
            # Ollama may ignore bool for GPT-OSS, but Zed sends true/false; pass through false
            # so clients can attempt disable; map true -> medium (required levels for GPT-OSS).
            if think is False:
                return False
            return "medium"
        if isinstance(think, str):
            level = _normalize_level_str(think)
            if level:
                return level
            return think
        return None
    return think


def resolve_ollama_think(
    body: dict[str, Any],
    reasoning_level: str | None,
    model_name: str | None,
) -> bool | str | None:
    """
    Priority: explicit `think` > `reasoning_effort` > derived `reasoning_level` (low/medium/high).

    Returns a value suitable for Ollama /api/chat `think`, after model-specific coercion, or None to omit.
    """
    if "think" in body:
        return coerce_think_for_model(_parse_think_value(body.get("think")), model_name)

    effort = body.get("reasoning_effort")
    if effort is not None and effort != "":
        if isinstance(effort, str):
            level = _normalize_level_str(effort)
            if level:
                return coerce_think_for_model(level, model_name)
            return coerce_think_for_model(effort.strip(), model_name)
        if isinstance(effort, bool):
            return coerce_think_for_model(effort, model_name)

    if reasoning_level and str(reasoning_level).strip().lower() in REASONING_LEVEL_VALUES:
        return coerce_think_for_model(str(reasoning_level).strip().lower(), model_name)

    return None


__all__ = ["coerce_think_for_model", "resolve_ollama_think"]
