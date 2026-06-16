# Quality gate profiles

Run gates from the repository root:

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile full
python scripts/quality_gate.py --profile release --include-advisory
```

## Profiles

| Profile | Purpose | Required steps |
|---------|---------|----------------|
| `minimal` | Every PR / local pre-push | `ruff`, `pytest -m fast`, `pytest --collect-only`, CoreUI `build`, `knip`, lockfile check |
| `full` | Main branch / nightly | `minimal` superset: `vulture`, full `pytest`, oversized-file audit (advisory), `lint-imports`, API drift-check (advisory), CoreUI `lint` + `test` + `typecheck` when configured |
| `strict-lint` | Incremental ruff expansion | `ruff` with import (`I`) and selected bugbear rules |
| `release` | Pre-tag / deploy candidate | `full` + `pyright`, `scripts/run_dependency_audit.py` (required), `docker build` (required when Docker available), `startup_smoke.sh` (required on Linux) |

## Advisory vs required

- **Required** failures block the gate (`exit 1`).
- **Advisory** failures are printed but do not fail `minimal` / `full` until promoted (e.g. oversized audit → required after baseline exceptions are documented).

## Related scripts

- `scripts/audit_oversized_files.py --mode check` — line-count policy (800 production / 1200 tests).
- `scripts/check_api_drift.py` — Flask routes ↔ OpenAPI ↔ CoreUI `api.js` (advisory in `full`).
- `reports/baseline/` — one-time and snapshot baseline outputs.
