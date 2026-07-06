# ADR 0007: Builtin Custom OpenAI-Compatible Upstream Providers

## Status

Accepted (2026-07-06)

## Context

ChironAI exposes an OpenAI-compatible **downstream** API (`/v1/chat/completions`, `/v1/models`) for IDE agents. **Upstream** LLM backends today are primarily registered through extensions (`ollama-provider`, cloud gateways). Operators frequently need arbitrary OpenAI-compatible gateways (OpenRouter, LM Studio, vLLM, corporate proxies) without authoring an extension.

Alternatives considered:

1. **Bundled `openai-compatible-provider` extension** — keeps all providers in the extension model but still requires extension install/enable UX and duplicates host settings wiring.
2. **LiteLLM sidecar** — powerful routing, heavy operational footprint, out of scope for v1.
3. **Builtin host runtime provider** — first-class CRUD in WebUI, persisted in `app_settings`, synced into the shared `LLMRuntime` registry.

## Decision

Implement **builtin host-managed custom providers**:

1. **Persistence** — JSON array in `app_settings` key `custom_openai_providers` (`Core/application/custom_openai_providers.py`). API keys stored server-side only; public DTOs mask secrets.
2. **Runtime** — `OpenAICompatibleProvider` (`Core/application/openai_compatible_provider.py`) implements the host provider contract (chat, streaming, model listing, health).
3. **Registry sync** — `sync_custom_openai_providers` (`Core/application/host_provider_sync.py`) registers/replaces custom providers in the extensions `LLMRuntime` registry on CRUD and at manager bootstrap.
4. **WebUI** — dedicated **Providers** sidebar tab for custom CRUD + extension summary; build wizard reads merged provider catalog from `/api/webui/providers/catalog`.
5. **Not an extension** — custom OpenAI-compat upstream is host-owned. Extension LLM providers remain the path for Docker services, sandboxing, and third-party packaging.

## Consequences

- **Positive:** Operators add upstream gateways in minutes; builds reference custom `provider_id` like extension providers; no extension boilerplate for standard OpenAI HTTP APIs.
- **Positive:** Single catalog surface for build wizard and Model Tester.
- **Negative:** Host owns another security-sensitive surface (API keys in SQLite settings). LAN exposure still depends on auth decisions (see P1.1 / P1.20).
- **Neutral:** Extension providers unchanged; bundled `ollama-provider` remains the canonical Ollama path.

## References

- Pre-Release P1.24 epic
- ADR 0002 (extension system), ADR 0003 (LLM proxy compat)
- `Core/data/webui/help/providers.md`
