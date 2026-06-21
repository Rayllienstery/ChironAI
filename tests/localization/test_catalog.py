"""Localization catalog tests (shared CoreModules/Localization)."""

from __future__ import annotations

from localization.catalog import SUPPORTED_LOCALES, available_locales, load_catalog, t


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


def test_en_xa_catalog_has_same_keys_as_en() -> None:
    en_keys = set(load_catalog("en").keys())
    xa_keys = set(load_catalog("en-XA").keys())
    assert en_keys == xa_keys


def test_supported_locales_are_registered_and_complete() -> None:
    en_keys = set(load_catalog("en").keys())

    assert "ru" in SUPPORTED_LOCALES
    assert set(available_locales()) == set(SUPPORTED_LOCALES)
    for locale in SUPPORTED_LOCALES:
        catalog = load_catalog(locale)
        assert set(catalog.keys()) == en_keys
        assert all(str(value).strip() for value in catalog.values())


def test_t_resolves_ru_catalog() -> None:
    assert t("nav.settings", locale="ru") == "Настройки"
