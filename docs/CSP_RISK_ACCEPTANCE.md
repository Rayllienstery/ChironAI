# Content Security Policy — risk acceptance (0.8.x)

ChironAI serves CoreUI from the same Flask host and applies CSP via `Core/api/http/security_headers.py`.

## Current policy

```
script-src 'self' 'unsafe-inline' 'unsafe-eval';
style-src 'self' 'unsafe-inline';
```

Tests in `tests/webui/test_webui_security_headers.py` (P2.9a) lock this policy. HSTS is sent only on HTTPS requests (P2.9b).

## Vite spike (P2.9c)

| Surface | `unsafe-eval` needed? | `unsafe-inline` needed? | Notes |
|---------|----------------------|-------------------------|-------|
| `npm run build` + `dist/` in production | **No** for typical Vite 5 React bundles | **Partial** — inline boot/preboot snippets in `index.html` and theme bootstrap | Production assets are hashed ES modules from `'self'`. |
| `npm run dev` (Vite HMR) | **Yes** | **Yes** | Dev server is not covered by Flask CSP; operators use Vite on `:3000` with API proxy. |
| Storybook | **Yes** (Storybook runtime) | **Yes** | Dev/docs only; not served by production Flask. |

**Conclusion:** Removing `'unsafe-eval'` from the **production** CSP is feasible for the built CoreUI bundle and should be attempted in a follow-up that runs full CoreUI + Playwright smoke against a strict CSP. Removing `'unsafe-inline'` requires nonce/hash wiring for `index.html` preboot and any remaining inline handlers (tracked under P1.4).

## Risk acceptance (0.8.x STABLE)

For localhost-first deployments (ADR 0008), the project **accepts** `'unsafe-inline'` and `'unsafe-eval'` in the Flask CSP because:

1. Primary threat model is trusted-local operator, not hostile web origin embedding.
2. Tightening CSP without breaking preboot, extension iframes, or Swagger UI needs dedicated QA.
3. Production `dist/` does not rely on `eval()` at runtime; `unsafe-eval` is defense-in-depth debt, not an active requirement for bundled JS.

**Promotion criteria (future):** drop `'unsafe-eval'` when Playwright + manual tab smoke pass with strict CSP; drop `'unsafe-inline'` when preboot/theme scripts use nonces or external files only.

## Related tickets

- P1.4 — full CSP hardening (blocked on Vite/preboot work above)
- P2.9a/b — tests for current policy
- P2.9c — this spike document
