## Summary

- 

## Verification

- [ ] Relevant gate from `Way to 1000.md` passed.
- [ ] `build_and_run.bat` was run for non-documentation changes, or the reason it could not run is documented.

## AI_RULES Checklist

- [ ] WebUI API changes are synchronized across contracts, CoreUI client, Flask routes, and OpenAPI docs.
- [ ] Added, changed, or removed HTTP endpoints include RESTX/OpenAPI docs, models, and spec coverage.
- [ ] Removed UI/API surfaces are cleaned from imports, routes, clients, constants, tests, styles, showcase, and docs.
- [ ] Domain import boundaries remain clean.
- [ ] Config or environment changes are documented for users and deploys.
- [ ] New long-lived monolith tails are documented in `docs/legacy_map.md`.
- [ ] CoreUI changes reuse existing tokens, tab patterns, lazy loading, and showcase entries where relevant.
- [ ] Extension changes provide required manifest, provider entry point, UI frame/title/icon/assets, and Docker runtime contracts.
- [ ] Version was bumped and `CHANGELOG.md` was updated.
