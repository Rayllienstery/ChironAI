# ADR 0008: WebUI Authentication Model

## Status

Accepted (2026-07-06)

## Context

All `/api/webui/*` routes are unauthenticated. Extension management, LLM Proxy API-key reveal/regenerate, custom provider CRUD, and settings mutation are available to any client that can reach the bind address. README and SECURITY.md already warn against public internet exposure.

Alternatives considered:

1. **Local-only by default** — bind `127.0.0.1`, document reverse-proxy + TLS for remote access; no WebUI login in v1.
2. **Built-in auth** — admin password or session gate when `host != 127.0.0.1`; higher UX and test surface before STABLE operators need LAN sharing.

P1.2 / P1.18 closes the config gap: bundled `server.yaml` now defaults to `127.0.0.1`, matching `get_server_host()` fallback and CHANGELOG 0.8.0 intent.

## Decision

Adopt **local-only by default** (option 1) for the STABLE line:

1. **Default bind** — `server.yaml` → `server.host: 127.0.0.1`. Override via `SERVER_HOST` or YAML for trusted LAN.
2. **No built-in WebUI auth in 0.8.x** — operators who bind `0.0.0.0` or expose the port must use firewall rules, VPN, or an authenticating reverse proxy.
3. **LLM Proxy `/v1/*`** remains API-key gated independently of WebUI auth.
4. **Future work** — built-in auth (P1.1.2) is deferred until a concrete LAN/multi-user requirement is prioritized; P1.20 (unauthenticated api-key reveal routes) is mitigated by local bind + documentation until then.

## Consequences

- **Positive:** Secure out-of-the-box default; no login friction for solo local development.
- **Positive:** Single documented story across README, SECURITY.md, and config.
- **Negative:** LAN operators must consciously opt in to `0.0.0.0` and accept full WebUI trust boundary.
- **Neutral:** Reverse-proxy auth (OAuth, basic auth, mTLS) remains the recommended production pattern for remote access.

## References

- Pre-Release P1.1, P1.2, P1.18, P1.20
- ADR 0007 (custom providers — API keys server-side)
- `SECURITY.md` — Known Security Boundaries
