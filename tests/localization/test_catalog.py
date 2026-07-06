"""Localization catalog tests (shared CoreModules/Localization)."""

from __future__ import annotations

from localization.catalog import SUPPORTED_LOCALES, available_locales, load_catalog, t


def test_load_catalog_en() -> None:
    catalog = load_catalog("en")
    assert catalog["app.title"] == "ChironAI"


def test_t_returns_message_id_when_missing() -> None:
    assert t("missing.id") == "missing.id"


def test_uk_catalog_has_same_keys_as_en() -> None:
    en_keys = set(load_catalog("en").keys())
    uk_keys = set(load_catalog("uk").keys())
    assert en_keys == uk_keys


def test_supported_locales_are_registered_and_complete() -> None:
    en_keys = set(load_catalog("en").keys())

    assert SUPPORTED_LOCALES == ("en", "uk")
    assert set(available_locales()) == set(SUPPORTED_LOCALES)
    for locale in SUPPORTED_LOCALES:
        catalog = load_catalog(locale)
        assert set(catalog.keys()) == en_keys
        assert all(str(value).strip() for value in catalog.values())


def test_t_resolves_uk_catalog() -> None:
    assert t("nav.settings", locale="uk") == "Налаштування"
