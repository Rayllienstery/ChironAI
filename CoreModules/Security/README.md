# Security

Security contains reusable static audit helpers for ChironAI extension safety.
It is intentionally small and focused so high-risk extension checks remain auditable.

## Purpose

- Audit extension backend source before loading or installing providers.
- Detect direct Docker CLI or SDK usage from extension code.
- Detect unsafe manifest paths and URLs.
- Return structured findings that callers can surface in diagnostics.

## Setup

- Install with `pip install -e CoreModules/Security`.
- The package is imported as `chironai_security`.
- It is used by LlmInteractor during extension discovery and installation.
- Keep checks deterministic and local; do not require network access.

## Entrypoints

- `chironai_security.audit_extension` returns an audit report.
- `chironai_security.audit_extension_or_raise` raises on blocking findings.
- `chironai_security.format_blocking_error` converts findings to readable errors.
- `chironai_security.extension_audit.backend_source_paths` resolves backend files.

## Audit Scope

- Extension manifests named `chironai-extension.json`.
- Backend provider entrypoints declared in the manifest.
- Python source files reachable from the backend entrypoint.
- Static policy checks that protect host capabilities.

## Testing

- Run `pytest -q tests/security`.
- Run extension backend tests after changing blocking finding codes.
- Add regression tests for every new policy rule.
- Keep finding codes stable because tests and UI diagnostics may depend on them.

## Dependencies

- Python standard library AST and path handling.
- LlmInteractor consumes this package but this package should not depend on LlmInteractor runtime.
- Docker policy remains declarative here; actual Docker execution belongs to DockerManager.
