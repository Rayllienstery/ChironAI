# Contributing to ChironAI

This guide describes the expected branch, commit, pull request, quality gate,
and versioning flow for ChironAI contributors.

## Branches

- Create focused branches from the current integration branch.
- Use short names that identify the work area, for example
  `docs/onboarding`, `coreui/e2e-smoke`, or `llmproxy/chat-split`.
- Keep one roadmap task or one cohesive fix per branch unless the dependency is
  explicit in `Way to 1000.md`.
- Do not mix generated output, dependency updates, and behavior changes unless
  the task requires them.

## Commits

Use Conventional Commits. The repository is configured for Commitizen with
`cz_conventional_commits` in `pyproject.toml`.

Common prefixes:

- `feat:` for user-visible features.
- `fix:` for bug fixes.
- `docs:` for documentation-only changes.
- `test:` for test-only changes.
- `refactor:` for behavior-preserving code movement.
- `chore:` for tooling, dependency, and maintenance changes.

Examples:

```text
docs: add contributor onboarding guide
test: add CoreUI accessibility smoke
refactor: split LlmProxy chat handler
```

## Pull Requests

Every pull request should include:

- A concise summary of the changed behavior or documentation.
- The relevant `Way to 1000.md` task ID when applicable.
- Verification commands and results.
- Notes about intentionally skipped checks or unrelated failures.
- Confirmation that the AI_RULES checklist in the PR template was reviewed.

Use `.github/pull_request_template.md` as the required checklist. If a change
touches a high-risk area from `AI_RULES.md`, call that out explicitly in the PR
summary.

## Quality Gates

Run gates from the repository root:

```bash
python scripts/quality_gate.py --profile minimal
python scripts/quality_gate.py --profile full
python scripts/quality_gate.py --profile release --include-advisory
```

Use the minimal profile for ordinary PRs. Use the full profile before merging
larger refactors, route changes, CoreUI test expansion, or module boundary work.
Use the release profile for pre-tag or deploy candidates.

Useful targeted checks:

```bash
python scripts/check_version_drift.py
python scripts/check_api_drift.py --strict --strict-openapi
python scripts/audit_oversized_files.py --mode check
npm --prefix CoreModules/CoreUI run build
```

For non-documentation changes, run `build_and_run.bat` as a startup smoke and
wait for the `Server ready` line. The process is long-running; stop the launched
backend processes after readiness is confirmed.

## Version and Changelog

Project tasks that change code or tooling must bump the version and update
`CHANGELOG.md`.

The canonical version is `Core/core/version.py`. Keep it synchronized with
`pyproject.toml` and the Commitizen version:

```bash
python scripts/check_version_drift.py
python scripts/sync_version.py --dry-run
```

When bumping manually, update:

- `Core/core/version.py`
- `pyproject.toml` project version
- `pyproject.toml` `[tool.commitizen].version`
- `CHANGELOG.md`

## AI_RULES Checklist

Before finishing a change, review `AI_RULES.md`:

- WebUI API changes stay synchronized across contracts, CoreUI client, Flask
  routes, RESTX/OpenAPI docs, and generated API types.
- HTTP endpoint changes include spec coverage and drift checks.
- Removed UI/API surfaces are cleaned from imports, routes, client methods,
  constants, tests, styles, showcase entries, and docs.
- `Core/domain/` import boundaries remain clean.
- Config and environment changes are documented.
- New long-lived migration tails are documented in `docs/legacy_map.md`.
- CoreUI changes use existing tokens, tab patterns, lazy loading, and showcase
  entries where relevant.
- Extension changes keep manifests, provider entry points, UI integration, and
  Docker runtime contracts intact.

## Repository Etiquette

- Preserve unrelated work in the working tree.
- Do not commit generated artifacts such as `CoreModules/CoreUI/dist/`,
  `storybook-static/`, `coverage/`, `playwright-report/`, or `test-results/`.
- Prefer source-of-truth docs over duplicating architectural rules.
- Keep compatibility imports and public HTTP behavior stable unless a task
  explicitly changes them.
