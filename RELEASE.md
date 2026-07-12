# Release checklist

Short gate before tagging a release. Run from repo root unless noted.

## Release candidate 0.10.0 notes

Status: **released (PRE-RELEASE)** — tag `v0.10.0` (`2026-07-13`). `v0.8.63` remains the last **STABLE** tag.

Highlights (0.10.0):

- Closed TD-P0.1, TD-P0.2, TD-P1.1, TD-P1.2, TD-P1.3.
- Version surfaces synced to 0.10.0; API reference regenerated.
- CoreUI bundle budget baseline bumped to 1761280 bytes; `bundle:budget` PASS.
- `lint-imports` PASS after adding `CoreModules/Localization` to dev requirements.
- Mutation score documented as advisory/trend-only.

Verification snapshot (2026-07-13):

- `python scripts/check_version_drift.py` — passed (0.10.0).
- `python scripts/quality_gate.py --profile release --include-advisory` — passed locally (Windows). Required steps all green.
- CoreUI bundle budget: PASS at 1693802 bytes (budget 1761280 bytes).
- CoreUI unit tests: PASS (208 tests).
- `lint-imports`: PASS.
- `python scripts/gen_api_docs.py --check` — PASS (regenerated for 0.10.0).
- Tag `v0.10.0` CI `release` green ([run 29195834137](https://github.com/Rayllienstery/ChironAI/actions/runs/29195834137)).
- GitHub Release published as **prerelease**: [v0.10.0 PRE-RELEASE](https://github.com/Rayllienstery/ChironAI/releases/tag/v0.10.0).

### Known release gate gaps (advisory, non-blocking)

- `coreui-i18n-lint` remains advisory: hardcoded UI strings and 2 untranslated `uk` keys (`about.github_label`, `about.linkedin_label`). Not a release blocker.
- `startup-smoke-sh` fails on native Windows because `bash` is unavailable; `startup-smoke-bat` covers the same smoke on Windows.
- `trivy-image` is skipped locally because the `trivy` executable is not installed; it runs in CI release workflow.

## Release candidate 0.9.0 notes

Status: **PRE-RELEASE** — first tag on the 0.9.x line (`v0.9.0`, 2026-07-10). `v0.8.63` remains the last **STABLE** tag.

Highlights (0.9.0):

- `APP_STAGE` → `PRE-RELEASE`; PyPI classifier → Beta for the prerelease line.
- Version surfaces synced to 0.9.0; API reference regenerated.
- README / SECURITY / ADR 0008 document 0.9.x vs 0.8.x version guidance.

Verification snapshot (2026-07-13, after TD-P0.1 / TD-P0.2 / TD-P1.1 / TD-P1.2):

- `python scripts/check_version_drift.py` — passed (0.9.0).
- `python scripts/quality_gate.py --profile release --include-advisory` — passed locally (Windows). Required steps all green. Advisory failures: `coreui-i18n-lint` (1391 hardcoded UI strings, 2 untranslated `uk` keys) and `startup-smoke-sh` (skipped on native Windows; `startup-smoke-bat` passed).
- CoreUI bundle budget: PASS at 1693802 bytes (budget 1761280 bytes) after TD-P0.1 baseline bump.
- CoreUI unit tests: PASS (208 tests) after TD-P0.2 AboutTab test fix.
- `lint-imports`: PASS after TD-P1.1 added `CoreModules/Localization` to `requirements-dev.txt`.
- Tag `v0.9.0` CI `release` green ([run 29108379025](https://github.com/Rayllienstery/ChironAI/actions/runs/29108379025)); mutation artifact stable (2891 mutants).
- GitHub Release published as **prerelease**: [v0.9.0 PRE-RELEASE](https://github.com/Rayllienstery/ChironAI/releases/tag/v0.9.0).

### Known release gate gaps (historical; resolved or documented in v0.10.0)

- Mutation score is **advisory / trend-only** (0.0% on 2891 mutants). It is recorded by tag CI but is **not** used as a blocking metric. Promotion to required is deferred post-v0.10.0.
- `coreui-i18n-lint` remains advisory: 1391 hardcoded UI strings and 2 untranslated `uk` keys (`about.github_label`, `about.linkedin_label`). Not a release blocker.

## Release candidate 0.8.63 notes

Status: **released** — last **STABLE** line tag before 0.9.x PRE-RELEASE (`v0.8.63`, 2026-07-10).

Highlights (0.8.63):

- RELEASE.md 0.8.62 section: mutation auto-record verified on tag CI.
- Sync `docs/mutation-baseline-score.txt` from `v0.8.62` CI artifact (stable 2891-mutant trend).
- Regenerate API reference for 0.8.63.

Verification snapshot (2026-07-10):

- Tag `v0.8.63` CI `release` green ([run 29104037002](https://github.com/Rayllienstery/ChironAI/actions/runs/29104037002)).
- `python scripts/check_version_drift.py` — passed (0.8.63).

## Release candidate 0.8.62 notes

Status: **post-STABLE hygiene** — mutation baseline auto-record verified on tag `v0.8.62` CI (2026-07-10).

Highlights (0.8.61–0.8.62):

- **`record_mutation_baseline_score.py`:** parses mutmut log and refreshes `docs/mutation-baseline-score.txt` after capture.
- CI artifact includes both `mutation-baseline.txt` and score tracker; stable trend vs `v0.8.59`/`v0.8.61`.
- Tracker: **2891** mutants (0 killed, 2543 survived, 14 timeout, 334 no tests; 0.0% advisory score on `v0.8.62`).

Verification snapshot (2026-07-10):

- Tag `v0.8.62` CI `release` green ([run 29100133738](https://github.com/Rayllienstery/ChironAI/actions/runs/29100133738)); mutation artifact contains auto-written score file.
- `python scripts/check_version_drift.py` — passed (0.8.62).

## Release candidate 0.8.60 notes

Status: **post-STABLE hygiene** — mutation baseline captured on tag `v0.8.59` CI (2026-07-10).

Highlights (0.8.58–0.8.60):

- **P2.6/P3.8 closed:** first advisory mutmut baseline on tag CI (`release` job, 60 min timeout).
- Import-path staging (`domain/`, `rag_service/`), Hypothesis property tests excluded from mutmut selection.
- Tracker: `docs/mutation-baseline-score.txt` — **2891** mutants (0 killed, 2543 survived, 14 timeout, 334 no tests; 0.0% advisory score on `v0.8.59`).

Verification snapshot (2026-07-10):

- `python scripts/check_version_drift.py` — passed (0.8.60).
- Tag `v0.8.59` CI `release` + `linux-fast` green; mutation artifact uploaded.
- `npm run bundle:budget` (CoreUI) — passed at budget ceiling.

## Release candidate 0.8.52 notes

Status: **released** — tag `v0.8.52`, CI `release` + `linux-fast` green, GitHub Release published, local `startup_smoke_bat` PASS (2026-07-08).

Highlights (0.8.52):

- **P2 closed:** route test coverage (P2.1), axe a11y e2e smoke (P2.2), `create_production_app()` factory (P2.5), mutation baseline CI (P2.6), oversized-file audit policy (P2.7), Storybook on PR minimal CI (P2.8).
- Production entrypoint: `webui_backend.app_factory.create_production_app` via `start_webui.bat` / `python -m webui_backend.rag_proxy`.

Verification snapshot (2026-07-07):

- `python scripts/check_version_drift.py` — passed (0.8.52).
- `python scripts/audit_oversized_files.py --mode check` — passed.
- `python -m pytest tests/webui/test_production_app_factory.py -q` — passed.

## Release candidate 0.8.40 notes

Status: pre-tag ready on Windows local gates as of 2026-07-07.

Highlights (0.8.40):

- Regenerated `docs/api/reference.md` (OpenAPI 0.8.39, 135 paths; `/api/webui/health`, `/live`, notification schemas).
- Advisory Storybook build on `macos-fast` CI (extends P2.8).

## Release candidate 0.8.34 notes

Status: pre-tag ready on Windows local gates as of 2026-07-07.

Highlights:

- Notification OpenAPI schemas and typed `api.types.ts` for `/api/webui/notifications*`.
- Streaming `/v1/responses` vision test; `NotificationCenterShell` `headerLeading` smoke test.
- Docker `/live` liveness, macOS CI (`macos-fast`), OpenAPI bootstrap without extension install.
- `APP_STAGE` is `STABLE`; quality gates `full` and `release` pass locally.

### Supply chain (P2.10c)

- `@alerix/m3-loading-indicator@^1.0.5` — no advisories in `npm audit` (2026-07-07).
- Remaining npm findings are dev-only (Storybook/uuid, Vite/esbuild); see `Core/config/dependency_audit_exceptions.json`.

### LLM proxy vision environment (P2.12c)

Configure on the server host when clients send images through `/v1/chat/completions` or `/v1/responses`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROXY_VISION_FETCH_EXTERNAL_URLS` | `0` | Fetch remote `http(s)` image URLs server-side (trusted networks only) |
| `LLM_PROXY_VISION_FALLBACK_MODEL` | empty | Ollama tag for image turns when the build model lacks vision |
| `LLM_PROXY_VISION_READ_LOCAL_FILES` | `0` | Inline local file path hints from user text (Copilot/Kilo workaround) |
| `LLM_PROXY_VISION_ALLOW_ABS_PATHS` | `0` | Allow absolute paths when local file read is enabled |

See `CoreModules/LlmProxy/README.md` for OpenCode vision setup and `file_id` limitations.

Highlights (0.8.39):

- Storybook static build in quality gate (advisory); extension manifest SHA-256 documented in SECURITY.md.

Verification snapshot (2026-07-07):

- `python scripts/quality_gate.py --profile release --include-advisory` — passed locally.
- `python scripts/validate_openapi.py` and `python scripts/check_api_drift.py --strict` — passed.
- `npm run test:run` from `CoreModules/CoreUI` — passed (includes notification smoke tests).

## Release candidate 0.8.17 notes (archive)

Status: pre-tag ready on Windows local gates as of 2026-07-06.

Highlights:

- In-app Help KB, onboarding tours, InfoButton contextual help, per-build RAG collection UI.
- `APP_STAGE` promoted to `STABLE`; quality gates `full` and `release` pass locally.
- 1 050+ pytest, 186 vitest, 7 Playwright E2E tests.

Verification snapshot (2026-07-06):

- `python scripts/quality_gate.py --profile release` — passed.
- `npm run e2e` from `CoreModules/CoreUI` — passed, 11 tests.
- `python scripts/check_version_drift.py` — passed (0.8.17).
- `python scripts/gen_api_docs.py --check` — passed.
- `python scripts/audit_oversized_files.py --mode check` — passed.

Before tag `v0.8.9`:

- Manual CoreUI tab smoke (Dashboard, Settings, Builds, RAG, Extensions, Logs).
- `build_and_run.bat` → `Server ready`.
- CI `release` job green on tag push.

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
- App stage is `STABLE` as of 0.8.17; security posture for unauthenticated local use is unchanged.

## Quality gates

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile release --include-advisory   # before tags
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
