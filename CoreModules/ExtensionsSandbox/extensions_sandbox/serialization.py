"""JSON-safe serialization helpers for sandbox RPC."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, SimpleNamespace):
        return to_jsonable(vars(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)
