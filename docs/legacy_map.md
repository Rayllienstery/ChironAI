# Legacy Map

Updated: 2026-06-01

Active cleanup roadmap: [`QUALITY_AUDIT.md`](../QUALITY_AUDIT.md).

## System Map

```text
CoreUI (RAG Tests / Notifications / Builds)
  -> api/http/webui_routes.py (+ webui_*_routes.py splits)
      -> application/rag_tests/*
      -> application/rag/proxy_settings_contract.py (monolith boundary helpers)
      -> rag_service.application.params / rag_service.application.use_cases
      -> CoreModules/RagService/rag_service/*
      -> RagRuntime + DockerManager (Qdrant service control)
  -> CoreModules/LlmProxy/llm_proxy/*
      -> OpenAI/Anthropic compatibility surface
      -> same RAG context build path (rag_service.application.use_cases)
```

## Legacy Clusters

## Root freelance runtime folders

- Current root-level runtime folders (`api/`, `application/`, `domain/`,
  `infrastructure/`, `config/`, `core/`, `modules/`, `prompts/`) are migration
  tails.
- Target ownership:
  - host layers move under `Core/`;
  - host-owned services move under `Core/modules/`;
  - reusable modules stay or move under `CoreModules/`;
  - prompt templates get an explicit owner instead of remaining root runtime
    data.

Risk: startup-critical code can become invisible ownership debt if it remains
at the repository root with no documented owner.

Guardrail target: add a root source allowlist test that rejects new importable
runtime package folders at the repository root unless they are explicitly
documented.

## A) Configuration/authority overlap

- Multiple config sources for similar behavior:
  - `proxy_settings` JSON blob,
  - dedicated `app_settings` fields,
  - yaml/env fallback.
- Documented precedence: [`config/CONFIG_AUTHORITY.md`](../config/CONFIG_AUTHORITY.md),
  env index: [`config/ENV_REFERENCE.md`](../config/ENV_REFERENCE.md).
- Main files:
  - `api/http/webui_settings_routes.py`, `webui_rag_routes.py`
  - `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py`
  - `api/http/llm_proxy_wiring.py`

Risk: hidden runtime divergence (mitigated by precedence tests in `tests/config/`).

## B) WebUI routes composition

- `api/http/webui_routes.py` is the composition root (~255 lines): blueprint bootstrap,
  `register_*` calls, RAG trigger helpers, legacy Ollama model defaults.
- Domain routes live in `webui_*_routes.py` (chat, rag, model tester, llm proxy,
  crawler, docker, extensions, observability, prompts, sessions, settings, performance,
  testing, provider helpers module).

Risk: low after Pass 4 split; regressions show up in `pytest tests/api tests/webui`.

## C) Protocol compatibility surface

- Intentional compatibility endpoints and request shapes:
  - `/v1/chat/completions`
  - `/v1/messages`
  - `/v1/responses`
  - OpenAI/provider message and tool normalization
- Main files:
  - `CoreModules/LlmProxy/llm_proxy/v1_blueprint.py`
  - `extensions/bundled/ollama-provider/backend/provider.py`

Risk: complexity if undocumented; low risk if treated as explicit contract.

Current ownership: the core proxy no longer registers raw Ollama-compatible
routes or legacy `/v1/completions`. Ollama-native compatibility behavior belongs
inside `ollama-provider`; core routes use provider/runtime contracts and fail
clearly when the provider runtime is unavailable.

## G) LLM provider boundary (formerly direct Ollama in core)

- Root `infrastructure/ollama/*` adapter files have been removed; the directory
  may still exist empty in local checkouts. Provider behavior belongs in
  `chironai-extension-ollama-provider` (`extensions/bundled/ollama-provider` is
  the trusted bootstrap mirror).
- Core embed/rerank/chat use `rag_service.infrastructure.provider_runtime` over
  `LLMRuntime` (`runtime_hooks` registers the runtime from the main app).
- LlmProxy wire-format helpers live under `llm_proxy/wire_format/` and
  `rag_service.infrastructure.openai_*` for public HTTP compatibility only.
- LlmProxy keeps `llm_proxy/ollama_compat.py` and `llm_proxy/wire_format/*` as
  explicit OpenAI/provider wire-format compatibility boundaries for `/v1`.
- Config keeps deprecated `get_ollama_*` env/yaml names; app code should prefer
  `get_default_chat_model`, `get_default_embed_model`, `get_default_rerank_model`.

Guardrail: `tests/application/test_ollama_migration_guardrails.py` rejects any
`from infrastructure.ollama` import in core trees.

## D) Retrieval mode compatibility

- Dense-only + hybrid + named dense compatibility in Qdrant repositories.
- Documented: [`CoreModules/RagService/docs/QDRANT_VECTOR_MODES.md`](../CoreModules/RagService/docs/QDRANT_VECTOR_MODES.md).
- Main files:
  - `CoreModules/RagService/rag_service/infrastructure/qdrant_repository.py`
  - `infrastructure/qdrant/rag_repository_impl.py` (shim)

Risk: hybrid vs dense-only mismatch; guarded by `tests/rag_service/test_qdrant_vector_modes.py`.

## E) Service control split

- WebUI-level Qdrant actions now delegate to RagRuntime; extension-owned
  services use DockerManager host capabilities.
- Main files:
  - `api/http/service_control.py`
  - `CoreModules/RagService/rag_service/runtime.py`

Risk: keep Qdrant status/ports aligned between WebUI and RagRuntime.

## F) UI integration legacy tails (mostly reduced)

- Event-based cross-tab open flow remains.
- Main files:
  - `CoreModules/CoreUI/src/App.jsx`
  - `CoreModules/CoreUI/src/components/NotificationCenterShell.jsx`
  - `CoreModules/CoreUI/src/components/RagTestsTab.jsx`

Risk: medium-low; manageable with explicit state contract.

## Keep vs Remove

Keep (intentional compatibility):
- `/v1/chat/completions`, `/v1/messages`, and `/v1/responses`.
- OpenAI/provider message, tool, and vision wire-format mapping used by `/v1`.
- Provider runtime and extension action contracts.

Remove (technical legacy):
- core raw Ollama-compatible route ownership and direct `localhost:11434` fallbacks.
- dead compatibility wrappers around stable internal contracts.
- global UI shims and implicit state globals.
- route-layer orchestration that belongs in application services.

## Suggested Sequence

1. Extract RAG Tests backend from `webui_routes.py`.
2. Lock config authority table and enforce in code.
3. Reduce Qdrant compatibility branches.
4. Normalize UI action dispatch to state-only flow.
5. Review compatibility endpoints and either bless or deprecate.
