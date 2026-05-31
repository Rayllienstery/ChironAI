"""Helpers for identifying Google Gemini model ids in routing strings."""

from __future__ import annotations

import re


def is_gemini_family_model_name(model_name: str | None) -> bool:
    """
    True when the provided string looks like a Google Gemini family model id.

    This is intentionally permissive across proxy routing prefixes/suffixes, e.g.:
    - gemini-*, google/gemini-*, models/gemini-*, *:cloud
    """
    raw = str(model_name or "").strip().lower()
    if not raw:
        return False
    tokens = [t for t in re.split(r"[^a-z0-9]+", raw) if t]
    if not tokens:
        return False
    return any(tok.startswith("gemini") for tok in tokens)
