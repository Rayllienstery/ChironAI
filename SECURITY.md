# Security Policy

## Supported Versions

The following versions of ChironAI currently receive security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.8.x   | :white_check_mark: |
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
- See [Extension registry provenance](#extension-registry-provenance) for supply-chain limits on installable extensions.
- **Default bind:** `server.yaml` sets `server.host` to `127.0.0.1`. For LAN access, set `SERVER_HOST=0.0.0.0` or edit `server.yaml` only on trusted networks.

## Authentication model (ADR 0008)

ChironAI **0.8.x** does not ship WebUI login. Security relies on **network placement**:

| Surface | Auth today | Mitigation |
|---------|------------|------------|
| `/api/webui/*` | None | Bind `127.0.0.1`; firewall; reverse proxy with auth for remote |
| `/v1/*` (LLM Proxy) | API key (`Authorization: Bearer` or `x-api-key`) | Rotate keys; use loopback-only WebUI routes to manage keys |
| `/api/webui/llm-proxy/api-key/generate` | Loopback client only | `POST` from `127.0.0.1` / `::1`; remote LAN clients get `403` |
| `/api/webui/llm-proxy/api-key/reveal` | Loopback client only | Same; mitigates LAN key theft when `SERVER_HOST=0.0.0.0` |
| `/api/webui/llm-proxy/api-key` `DELETE` | Loopback client only | Same |
| `/api/webui/llm-proxy/api-key` `GET` | None (metadata only) | Does not return plaintext key |
| Extension management | None (WebUI API) | Same as WebUI — localhost or trusted LAN only |

Built-in WebUI authentication is **deferred** until a prioritized LAN/multi-user requirement. See [`docs/adr/0008-webui-auth-model.md`](docs/adr/0008-webui-auth-model.md).

## Known Security Boundaries

- Extension install/update/remove/enable/disable routes are part of the WebUI API surface. These routes do **not** require authentication. Run ChironAI only on `localhost` or inside a trusted network, and treat any network that can reach the WebUI as having full extension-management access.
- Dependency vulnerabilities are monitored via `pip-audit`, `npm audit`, and Trivy image scans documented in `RELEASE.md`.

## Extension registry provenance

ChironAI can install extensions from a configured registry (default: GitHub-hosted JSON) or from local/bundled paths. **There is no full cryptographic signature verification** of third-party extension packages today.

| Risk | Current mitigation |
|------|------------------|
| Tampered or malicious registry entries | Blocklist policy (`ExtensionBlocklistPolicy`); manifest validation; install-time security audit |
| Compromised publisher or repository | Registry metadata + GitHub release/archive resolution; user consent on capability changes (see [`docs/EXTENSIONS_GITHUB_MIGRATION.md`](docs/EXTENSIONS_GITHUB_MIGRATION.md)) |
| Malicious extension code at runtime | Out-of-process sandbox workers; defense-in-depth only — not a sandbox escape guarantee |
| Unauthenticated install from LAN | Same as WebUI — bind `127.0.0.1` or restrict network access (ADR 0008) |

**Operator guidance:** treat extension install like running untrusted code. Use the default registry only from trusted networks, review extension permissions and publisher metadata before install, and prefer pinned versions over floating `latest`. Planned hardening (signature verification, immutable artifacts, SBOM) is tracked in [`docs/EXTENSIONS_GITHUB_MIGRATION.md`](docs/EXTENSIONS_GITHUB_MIGRATION.md).
