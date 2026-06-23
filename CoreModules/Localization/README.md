# Localization

Localization owns ChironAI text catalogs and catalog lookup helpers.
It is the shared source for UI strings that should be translated or pseudo-localized.

## Purpose

- Store language catalogs under `localization/catalog/`.
- Provide helpers for loading and validating localized keys.
- Support pseudo-localization during UI layout checks.
- Keep user-facing strings discoverable instead of scattering ad hoc literals.

## Setup

- Install with `pip install -e CoreModules/Localization`.
- Catalogs are plain JSON files grouped by locale.
- Current catalogs include English and pseudo-localized English variants.
- Add new locales by mirroring the existing catalog structure.

## Entrypoints

- Import catalog helpers from `localization.catalog`.
- Package exports live in `localization.__init__`.
- CoreUI integration should consume generated or served catalog data, not Python internals directly.
- Future locale registry changes should stay compatible with existing catalog paths.

## Catalog Rules

- Keep keys stable and descriptive.
- Do not remove keys without updating consumers.
- Add translated values for every key in the source catalog.
- Use pseudo-localization to catch clipping and hardcoded layout assumptions.

## Testing

- Run `pytest -q CoreModules/Localization/tests` when catalog helpers change.
- Add completeness checks when adding a new locale.
- Validate JSON syntax before committing catalog edits.
- Run CoreUI build when frontend catalog loading changes.

## Dependencies

- Python standard library JSON and path helpers.
- Optional consumers in CoreUI and backend API code.
- No dependency on RAG, LlmProxy, Docker, or extension runtime internals.
