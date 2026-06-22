# Security Policy

## Supported Versions

The following versions of ChironAI currently receive security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7.0 | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in ChironAI, please report it privately.

- **Email:** open a GitHub Security Advisory at `https://github.com/Rayllienstery/ChironAI/security/advisories/new` if you have access, or contact the maintainers through a private GitHub issue marked as sensitive.
- **Do not** open a public issue or pull request for security vulnerabilities.
- Please include:
  - A clear description of the vulnerability.
  - Steps to reproduce or a proof-of-concept.
  - The affected version(s) and component(s).
  - Any suggested mitigation or fix.

We aim to acknowledge reports within 5 business days and will coordinate disclosure once a fix is available.

## Security-Related Configuration

- Keep `.env` files and any generated API keys out of version control (see `.gitignore`).
- Rotate proxy API keys after installation or suspected compromise.
- Run extension code only from trusted sources; the extension sandbox and security audit are defense-in-depth, not a guarantee.

## Known Security Boundaries

- Extension install/update/remove routes are part of the WebUI API surface. Authentication and authorization for mutating routes are tracked in `docs/EXTENSIONS_GITHUB_MIGRATION.md` (Phase 8).
- Dependency vulnerabilities are monitored via `pip-audit`, `npm audit`, and Trivy image scans documented in `RELEASE.md`.
