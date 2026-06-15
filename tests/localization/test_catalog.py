"""Localization catalog tests (shared CoreModules/Localization)."""

from __future__ import annotations

from localization.catalog import load_catalog, t


def test_load_catalog_en() -> None:
    catalog = load_catalog("en")
    assert catalog["app.title"] == "ChironAI"


def test_t_returns_message_id_when_missing() -> None:
    assert t("missing.id") == "missing.id"


def test_load_catalog_en_xa_pseudo_locale() -> None:
    catalog = load_catalog("en-XA")
    assert catalog["app.title"].startswith("[!!")
    assert "ÇĥïŕöñÅÏ" in catalog["app.title"]


def test_t_en_xa_nav_labels_longer_than_en() -> None:
    en_label = t("nav.dashboard", locale="en")
    xa_label = t("nav.dashboard", locale="en-XA")
    assert len(xa_label) > len(en_label)
