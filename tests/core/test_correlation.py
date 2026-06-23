"""Tests for correlation id helpers."""

from __future__ import annotations

from core.shared.correlation import new_correlation_id, resolve_correlation_id


def test_new_correlation_id_is_non_empty_uuid() -> None:
    value = new_correlation_id()
    assert value
    assert len(value) == 36


def test_resolve_correlation_id_prefers_explicit_value() -> None:
    assert resolve_correlation_id("explicit-id") == "explicit-id"
