# Quality gate profiles

Run gates from the repository root:

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile full
python scripts/quality_gate.py --profile release --include-advisory
python scripts/quality_gate.py --profile mutation --include-advisory
```

## Profiles

| Profile | Purpose | Steps |
|---------|---------|-------|
| `minimal` | Every PR / local pre-push | See [minimal](#minimal) below |
| `full` | Main branch / nightly | `minimal` + [full extras](#full-extras) |
| `strict-lint` | Incremental ruff expansion | `ruff` with import (`I`) and selected bugbear rules |
| `mutation` | Advisory mutation baseline | `mutmut run` (advisory unless promoted) |
| `release` | Pre-tag / deploy candidate | `full` + [release extras](#release-extras) |

### minimal

| Step | Required |
|------|----------|
| `ruff check .` | yes |
| `bandit -r Core CoreModules` | yes |
| `scripts/check_version_drift.py` | yes |
| `scripts/check_api_drift.py --strict --strict-openapi` | yes |
| `scripts/validate_openapi.py` | yes |
| `pytest -m fast` | yes |
| `pytest --collect-only` | yes |
| CoreUI `npm run build` | yes |
| CoreUI `npm run bundle:budget` | yes |
| CoreUI `npm run knip` | yes |
| CoreUI `npm run check:lockfile` | yes |

### full extras

Everything in `minimal`, plus:

| Step | Required |
|------|----------|
| `vulture` | yes |
| `pytest` (full suite) | yes |
| `pytest -m fast` with `--cov=domain --cov=application --cov-fail-under=80` | yes |
| `scripts/audit_oversized_files.py --mode check` | yes |
| `scripts/audit_silent_exceptions.py --mode check` | advisory |
| `lint-imports` | advisory |
| `bandit` (second pass in full profile) | yes |
| `scripts/check_api_drift.py` (non-strict) | yes |
| CoreUI `npm run lint` | yes |
| CoreUI `npm run i18n-lint` | advisory |
| CoreUI `npm run test:run` | yes |
| CoreUI `npm run test:coverage` | yes |
| CoreUI `npm run typecheck` | yes |

### release extras

Everything in `full`, plus:

| Step | Required | Notes |
|------|----------|-------|
| `mypy Core/domain Core/core` | yes | |
| `pyright` | yes | |
| `scripts/run_dependency_audit.py` | yes | |
| `scripts/gen_api_docs.py --check` | advisory | Promote before tag when API docs changed |
| `docker build -t chironai:gate .` | yes when Docker available | Skipped if `docker` missing |
| `trivy image chironai:gate` | advisory | With `--include-advisory` |
| `scripts/startup_smoke.sh` | yes on Linux/WSL | Skipped on native Windows |
| `scripts/startup_smoke_bat.ps1` | advisory | Windows smoke helper |
| CoreUI `npm run e2e` | advisory | With `--include-advisory`; Playwright smoke |

## Platform parity

| Step | Windows (local) | Linux CI (`release` job) |
|------|-----------------|--------------------------|
| `pytest` / CoreUI tests | yes | yes |
| `mypy` / `pyright` | yes | yes |
| `docker build` | when Docker Desktop available | yes |
| `startup_smoke.sh` | skipped (`os.name == nt`) | required when `bash` available |
| `startup_smoke_bat.ps1` | advisory with `--include-advisory` | skipped |
| `mutmut` | advisory; prefer WSL/CI Linux | advisory with `--include-advisory` |
| Trivy image scan | advisory locally | advisory (`continue-on-error: true` in CI) |
| Codecov upload | n/a locally | advisory (`fail_ci_if_error: false` in CI) |

The `macos-fast` workflow job (`.github/workflows/quality.yml`) runs on `macos-latest` for pull requests and `main`/`master` pushes: `pytest -m fast`, CoreUI `npm run build`, and `npm run test:run`.

`scripts/quality_gate.py` sets `PYTHONPATH` for every subprocess step to mirror
`[tool.pytest.ini_options].pythonpath` (repo root, `Core`, `Core/modules/*`, and
`CoreModules/*` package roots). This lets advisory `lint-imports` resolve
`domain`, `llm_proxy`, `rag_service`, and other layer packages on Windows and
Linux without a manual editable install.

## Advisory vs required

- **Required** failures block the gate (`exit 1`).
- **Advisory** failures are printed but do not fail the profile unless promoted.
- Pass `--include-advisory` to execute advisory steps and count their failures on `full` / `release` / `mutation`.
- The oversized-file audit is required in `full`; generated files and documented baseline exceptions are excluded from hard failure.
- Mutation testing is advisory and expected to run on Linux/WSL. Native Windows `mutmut` may exit early; use WSL or CI Linux for baseline score collection.

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

Source of truth: `scripts/quality_gate.py` (`MINIMAL_GATE`, `FULL_GATE_EXTRA`, `RELEASE_TYPING_GATE`, `RELEASE_GATE_EXTRA`).
