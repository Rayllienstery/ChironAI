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
- [ ] `scripts/startup_smoke.sh` on Linux (when available)

## Changelog

- [ ] User-visible changes noted in `CHANGELOG.md`
- [ ] Breaking API changes: contract tests + changelog entry

## Security (release profile)

- [ ] `pip-audit` / `npm audit` — no undocumented high/critical findings
