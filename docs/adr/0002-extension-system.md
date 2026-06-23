# ADR 0002: Extension System with Manifests, Capabilities, and Sandboxed Runtime

## Status

Accepted

## Context

ChironAI needs to support third-party and bundled capabilities (Ollama provider, Open WebUI, custom RAG sources) without letting those capabilities destabilize the host. Early experiments mixed extension code with CoreUI and backend routes, creating ownership confusion and security risk. We decided to treat extensions as first-class, self-contained units with a declared contract.

## Decision

Every extension is a payload managed through the extension contracts and extension-management backend:

1. **Manifest:** Each extension root contains `chironai-extension.json` with `id`, `version`, `type`, and `capabilities`.
2. **Backend entry point:** The configured backend module exposes `create_provider(host_context, manifest)`.
3. **Capability enforcement:** An extension can only use capabilities declared in its manifest. The host rejects calls to undeclared capabilities.
4. **UI integration:** Extensions provide their own UI frame, tab title, tab icon, and assets. Integration is through supported points only:
   - `tab_ui` / `iframe_tab` for complex UIs.
   - `ui_schema` for declarative settings/status pages.
5. **Docker contract:** Extension-owned containers are declared with `DockerContainerSpec` and managed only through `host_context.docker_runtime`. Extensions must not call Docker directly, shell out, or call CoreUI `/api/webui/docker/*` routes.
6. **Security audit:** Bundled and staged extensions are audited for dangerous patterns (subprocess, eval, encoded commands, unsafe URLs) before loading.

## Consequences

- **Positive:**
  - Extensions are self-contained and cannot silently inject code into CoreUI.
  - The host can reason about what an extension is allowed to do before invoking it.
  - Docker ownership is centralized; extension bugs cannot bypass container management.
- **Negative:**
  - Extension authors must learn the manifest and capability model.
  - Some legacy extension integrations had to be rewritten to fit the iframe/schema model.
- **Neutral:**
  - `extensions/bundled/*` remain as trusted bootstrap/offline mirrors, but the canonical source for provider behavior (e.g., Ollama) is its dedicated extension repository.

## References

- `AI_RULES.md` section 4
- `extensions/bundled/*/chironai-extension.json`
- `CoreModules/ExtensionsHost/`
- `tests/extensions_backend/`
- `tests/security/test_extension_audit.py`
