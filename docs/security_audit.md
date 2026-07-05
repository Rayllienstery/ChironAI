# Security Audit Baseline

This page tracks advisory security scans that are not yet required to pass as
blocking gates.

## Bandit

- Date: 2026-07-05
- Command: `python -m bandit -r Core CoreModules -q -ll`
- Gate status: required in `scripts/quality_gate.py` (both `minimal` and `full` profiles)
- Current result: zero MEDIUM/HIGH findings
- Notes: 2026-07-05 — annotated false-positive B608 in `logs_repository.py` proxy journal GROUP BY queries (parameterized WHERE via `_build_proxy_journal_where`).

Summary from the initial baseline (2026-06-20):

| Severity | Count |
| --- | ---: |
| Low | 124 |
| Medium | 15 |
| High | 1 |

Common finding groups from the initial baseline:

- Subprocess and URL opening calls in Docker/WebUI startup and runtime helpers.
- Broad exception fallbacks in compatibility and runtime paths.
- SQL-construction warnings in repository helpers that need case-by-case review.
- Bind-all-interface defaults in local server startup configuration.

All MEDIUM/HIGH findings have been resolved: validated URL schemes before `urlopen`,
removed `shell=True` from subprocess calls, changed the default bind host to
`127.0.0.1`, applied security headers to the WebUI entrypoint, and annotated the
remaining false-positive B104/B608 findings with `# nosec` comments explaining why
they are safe. The `bandit` step now runs with `-ll` (MEDIUM/HIGH) and is required
to pass in both the `minimal` and `full` quality gate profiles.

## Secret Scanning

Gitleaks runs in CI through `.github/workflows/quality.yml`.

## Dependency Updates

Dependabot is configured in `.github/dependabot.yml` for Python, CoreUI npm
dependencies, and GitHub Actions.
