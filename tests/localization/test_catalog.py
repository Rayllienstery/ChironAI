"""Localization catalog tests (shared CoreModules/Localization)."""

from __future__ import annotations

from localization.catalog import load_catalog, t


def test_load_catalog_en() -> None:
    catalog = load_catalog("en")
    assert catalog["app.title"] == "ChironAI"


def test_t_returns_message_id_when_missing() -> None:
    assert t("missing.id") == "missing.id"
