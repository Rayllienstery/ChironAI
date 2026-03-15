"""
Pipeline and step schema for MD indexer.

Pipeline = { "name": "...", "steps": [ { "id": "...", "type": "...", "params": {...} }, ... ] }.
"""

from __future__ import annotations

from typing import Any

# Step types supported by the runner
STEP_TYPES = (
    "strip_meta_block",
    "delete_lines_exact",
    "delete_lines_containing",
    "delete_lines_regex",
    "delete_range_regex",
    "delete_regex_match",
    "strip_sections_by_heading",
    "normalize_whitespace",
    "replace_regex",
)


def _step_from_dict(d: dict[str, Any]) -> "Step":
    return Step(
        id=d.get("id", ""),
        type=d.get("type", ""),
        params=d.get("params") or {},
    )


class Step:
    """Single pipeline step."""

    __slots__ = ("id", "type", "params")

    def __init__(self, id: str, type: str, params: dict[str, Any]) -> None:
        self.id = id
        self.type = type
        self.params = params

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "params": self.params}


class Pipeline:
    """Pipeline definition: name + ordered steps."""

    __slots__ = ("name", "steps")

    def __init__(self, name: str, steps: list[Step]) -> None:
        self.name = name
        self.steps = steps

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Pipeline":
        name = d.get("name", "default")
        raw_steps = d.get("steps") or []
        steps = [_step_from_dict(s) if isinstance(s, dict) else s for s in raw_steps]
        return cls(name=name, steps=steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.steps],
        }
