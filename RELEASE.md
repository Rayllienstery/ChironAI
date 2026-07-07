# Release checklist

Short gate before tagging a release. Run from repo root unless noted.

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
