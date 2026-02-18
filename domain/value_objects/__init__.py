"""
Domain value objects.

Typed values used across the domain (reasoning level, doc type, etc.)
without infrastructure dependencies.
"""

from __future__ import annotations

from typing import Literal

ReasoningLevel = Literal["low", "medium", "high"]

REASONING_LEVEL_VALUES: tuple[ReasoningLevel, ...] = ("low", "medium", "high")


def is_valid_reasoning_level(s: str | None) -> bool:
    """Return True if s is a valid reasoning level."""
    return s in REASONING_LEVEL_VALUES


__all__ = [
    "ReasoningLevel",
    "REASONING_LEVEL_VALUES",
    "is_valid_reasoning_level",
]
