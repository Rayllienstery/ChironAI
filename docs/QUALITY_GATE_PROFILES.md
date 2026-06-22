# Quality gate profiles

Run gates from the repository root:

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile full
python scripts/quality_gate.py --profile release --include-advisory
python scripts/quality_gate.py --profile mutation --include-advisory
```

## Profiles

| Profile | Purpose | Required steps |
|---------|---------|----------------|
| `minimal` | Every PR / local pre-push | `ruff`, version drift, API drift, OpenAPI schema validation, `pytest -m fast`, `pytest --collect-only`, CoreUI `build`, `knip`, lockfile check |
| `full` | Main branch / nightly | `minimal` superset: `vulture`, full `pytest`, oversized-file audit, `lint-imports`, API drift-check (advisory), CoreUI `lint` + `test:run` + `test:coverage` + `typecheck` when configured |
| `strict-lint` | Incremental ruff expansion | `ruff` with import (`I`) and selected bugbear rules |
| `mutation` | Advisory mutation baseline for critical domain/RAG services | No required steps by default; with `--include-advisory`, runs `mutmut run` using `[tool.mutmut]` |
| `release` | Pre-tag / deploy candidate | `full` + `pyright`, `scripts/run_dependency_audit.py` (required), `docker build` (required when Docker available), `startup_smoke.sh` (required on Linux) |

## Advisory vs required

- **Required** failures block the gate (`exit 1`).
- **Advisory** failures are printed but do not fail `minimal` / `full` until promoted.
- The oversized-file audit is required in `full`; generated files and documented baseline exceptions are excluded from hard failure.
- Mutation testing is advisory and expected to run on Linux/WSL. Native Windows
  `mutmut` currently exits before running; use WSL or CI Linux for baseline
  score collection.

## Mutation baseline

The mutation baseline is configured through `[tool.mutmut]` in `pyproject.toml`.
It targets critical domain logic in `Core/domain/services` and
`CoreModules/RagService/rag_service/domain`, with focused test selection from
`tests/domain` and the RAG service retrieval/core/integration tests.

Baseline command:

```bash
python scripts/quality_gate.py --profile mutation --include-advisory
```

Baseline status on 2026-06-21: configured, but no numeric mutation score was
recorded on the native Windows workstation. `mutmut 3.6.0` exits before running
on native Windows and requires WSL; the workstation has WSL enabled but no Linux
distribution installed. Capture the first score from WSL or CI Linux and update
this section with the surviving/killed mutation counts.

## Related scripts

- `scripts/audit_oversized_files.py --mode check` - line-count policy (800 production / 1200 tests).
- `scripts/check_api_drift.py` - Flask routes, OpenAPI, and CoreUI `api.js` drift check.
- `scripts/gen_api_docs.py --check` - generated Markdown API reference freshness check.
- `scripts/validate_openapi.py` - generated OpenAPI 3.1 schema validation.
- `mutmut run` - advisory mutation baseline for `Core/domain/services` and
  `CoreModules/RagService/rag_service/domain`.
- `reports/baseline/` - one-time and snapshot baseline outputs.
