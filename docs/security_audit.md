# Security Audit Baseline

This page tracks advisory security scans that are not yet required to pass as
blocking gates.

## Bandit

- Date: 2026-06-20
- Command: `python -m bandit -r Core CoreModules -q`
- Gate status: advisory in `scripts/quality_gate.py`
- Current result: non-zero exit with existing findings

Summary from the initial baseline:

| Severity | Count |
| --- | ---: |
| Low | 124 |
| Medium | 15 |
| High | 1 |

Common finding groups:

- Subprocess and URL opening calls in Docker/WebUI startup and runtime helpers.
- Broad exception fallbacks in compatibility and runtime paths.
- SQL-construction warnings in repository helpers that need case-by-case review.
- Bind-all-interface defaults in local server startup configuration.

Triage these findings before making Bandit a required gate.

## Secret Scanning

Gitleaks runs in CI through `.github/workflows/quality.yml`.

## Dependency Updates

Dependabot is configured in `.github/dependabot.yml` for Python, CoreUI npm
dependencies, and GitHub Actions.
