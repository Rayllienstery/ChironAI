# ADR 0003: OpenAI-Compatible LLM Proxy Surface

## Status

Accepted

## Context

Cursor, Kilo, and other IDE agents expect an OpenAI-compatible chat endpoint at `/v1/chat/completions`. Some also use `/v1/messages` (Anthropic) and `/v1/responses` (OpenAI Responses API). We needed a single proxy layer that:

- Presents stable OpenAI/Anthropic request/response shapes to clients.
- Translates those shapes to and from Ollama and other provider runtimes.
- Keeps compatibility behavior separate from the core RAG pipeline so that protocol quirks do not leak into domain logic.

## Decision

`CoreModules/LlmProxy/` owns the public compatibility surface:

1. **Canonical endpoints:**
   - `/v1/chat/completions` — primary OpenAI-compatible chat endpoint.
   - `/v1/messages` — Anthropic-style messages endpoint.
   - `/v1/responses` — OpenAI Responses API shape.
   - `/v1/models` — model listing.
2. **Wire-format isolation:** Message, tool, vision, and reasoning normalization live in `llm_proxy/wire_format/` and `rag_service.infrastructure.openai_*` modules. Domain code does not deal with OpenAI multipart image parts or Anthropic thinking blocks directly.
3. **Provider runtime delegation:** The proxy ultimately calls provider runtimes (e.g., `ollama-provider`) through the host runtime contract, not by hardcoding `localhost:11434`.
4. **Intentional legacy:** Some legacy paths (e.g., old tool-stream behavior) are kept explicitly and documented as compatibility surface, not accidental debt.
5. **No raw Ollama routes in core:** Ollama-native behavior belongs in the `ollama-provider` extension. Core routes fail clearly when the provider runtime is unavailable.

## Consequences

- **Positive:**
  - IDE agents can point at ChironAI with standard OpenAI base URL settings.
  - Protocol changes are localized to LlmProxy instead of scattered across RAG and WebUI code.
  - The `tests/llm_proxy/` suite gives high confidence that compatibility shapes remain stable.
- **Negative:**
  - Maintaining three similar-but-different API shapes requires ongoing attention.
  - Legacy tool-stream paths add complexity that would otherwise be removed.
- **Neutral:**
  - The OpenAPI spec under `/api/webui/openapi.json` documents the public surface and is validated in CI.

## References

- `AI_RULES.md` section 7 (high-risk area 1)
- `CoreModules/LlmProxy/README.md`
- `CoreModules/LlmProxy/llm_proxy/v1_blueprint.py`
- `tests/llm_proxy/`
