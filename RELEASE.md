# Release checklist

Short gate before tagging a release. Run from repo root unless noted.

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
