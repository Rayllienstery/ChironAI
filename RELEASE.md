# Release checklist

Short gate before tagging a release. Run from repo root unless noted.

## Release candidate 0.7.56 notes

Status: release-candidate ready on Windows local gates as of 2026-06-22.

Highlights:

- Release gate now passes end to end with `python scripts/quality_gate.py --profile release`.
- CoreUI Docker builds can reuse committed API types when Python is unavailable in the Node build stage.
- Core contracts and generated OpenAPI normalization are clean under pyright.
- The release gate uses the dedicated CoreUI `test:run` script.
- Current transitive dependency audit findings are documented in `Core/config/dependency_audit_exceptions.json`.

Verification snapshot:

- `python scripts/quality_gate.py --profile release` - passed.
- `npm.cmd run e2e` from `CoreModules/CoreUI` - passed, 2 Playwright smoke tests.
- Live CoreUI UI pass for Dashboard, Settings, RAG / Qdrant, Extensions, Testing, and Logs - passed.
- `build_and_run.bat` startup smoke - reached `Server ready` at `http://127.0.0.1:8080/webui`; smoke processes were stopped afterward.

Known release notes:

- CoreUI lint still reports existing warnings but exits 0.
- Dependency audit passes with documented exceptions for current transitive Python/npm advisories.
- App stage remains `BETA`; changing the product stage should be a separate release decision.

## Quality gates

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile release   # before tags
```

## Backend

- [ ] `pytest -q` green (or `pytest -m fast` for a quick slice)
- [ ] `ruff check .` on changed Python files
- [ ] `python scripts/check_api_drift.py --strict` if API or CoreUI services changed
- [ ] `python scripts/import_smoke.py` after packaging changes

## CoreUI

From `CoreModules/CoreUI`:

```bash
npm run lint
npm run test:run
npm run e2e
npm run build
```

## Deploy smoke (release)

- [ ] `docker compose build` succeeds
- [ ] `docker compose up` — app responds on `/health` and `/ready`
- [x] `scripts/startup_smoke.sh` on Linux — verified in CI `linux-fast` job (CoreUI build + import smoke + ruff + fast pytest)

## Changelog

- [ ] User-visible changes noted in `CHANGELOG.md`
- [ ] Breaking API changes: contract tests + changelog entry

## Security (release profile)

- [x] `pip-audit` / `npm audit` — no undocumented high/critical findings (`python scripts/run_dependency_audit.py`)
- [x] Trivy image scan — advisory scan of `chironai:gate` in the release workflow
