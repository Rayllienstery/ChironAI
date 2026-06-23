# Legacy Map

Updated: 2026-06-21

Active cleanup tracking: this document and [`QUALITY_GATE_PROFILES.md`](QUALITY_GATE_PROFILES.md).

## Refactor status (Phases 0–5)

| Phase | Outcome |
|-------|---------|
| 0 | Root ownership allowlist (`scripts/root_layout_guard.py`) |
| 1 | Host layers under `Core/` with stable import names |
| 2 | Host services under `Core/modules/` |
| 3 | Prompt templates owned by `Core/modules/prompts_manager/` (`WebUI/prompts/` runtime store) |
| 4 | Extension host bridge in `CoreModules/ExtensionsHost/`; marketplace in `extensions_backend` |
| 5 | Legacy tails documented by owner; Qdrant listing + WebUI retrieval settings moved out of route composition |

## Legacy tail ownership

| Tail | Owner | Reason kept |
|------|-------|-------------|
| `Core/api/http/webui_routes.py` | Core/api | WebUI blueprint composition root only (registers `webui_*_routes`) |
| `Core/api/http/webui_*_routes.py` | Core/api | HTTP adapters per bounded context (chat, crawler, rag, prompts, extensions, …) |
| `Core/api/http/rag_tests_routes.py` | Core/api + `application/rag_tests` | RAG test orchestration split from WebUI composition |
| `Core/api/http/llm_proxy_wiring.py` | Core/api | Host wiring into `CoreModules/LlmProxy` (uses `ExtensionsHost`) |
| `Core/application/rag/proxy_settings_contract.py` | Core/application | Config authority helpers for proxy/RAG settings precedence |
| `Core/application/rag/webui_retrieval_settings.py` | Core/application | WebUI RAG trigger threshold + default model helpers |
| `Core/infrastructure/qdrant/collection_names.py` | Core/infrastructure | Shared Qdrant collection listing for WebUI, RAG tests, indexer |
| `CoreModules/LlmProxy/*` wire-format | LlmProxy | Intentional OpenAI/Anthropic compatibility surface |
| `extensions/bundled/*` | extensions + `extensions_backend` | Trusted bootstrap/offline mirrors only |

No root-level runtime packages remain except documented project support (`docs/`, `tests/`, `rag_tests/` fixtures, `WebUI/` data).

## Legacy tail exit criteria

| Tail | Removal trigger | Verification |
|------|-----------------|--------------|
| `Core/api/http/webui_routes.py` | Remove only if Flask blueprint composition moves to `webui_backend` without changing `/api/webui` contracts. | `pytest tests/api`, `python scripts/check_api_drift.py --strict --strict-openapi` |
| `Core/api/http/webui_*_routes.py` | Retire one route module only when its bounded context has a stable module-owned HTTP adapter. | Route-specific API tests plus OpenAPI drift check |
| `Core/api/http/rag_tests_routes.py` | Move when RAG test orchestration becomes a module with its own public HTTP contract. | `pytest tests/api/test_http_rag_tests* tests/application` |
| `Core/api/http/llm_proxy_wiring.py` | Remove only when LlmProxy can receive all dependencies through a stable host contract. | `pytest tests/llm_proxy tests/api/test_http_chat_completions.py` |
| `Core/application/rag/proxy_settings_contract.py` | Remove after all callers use typed settings DTOs and compatibility migration is complete. | `pytest tests/application/test_proxy_settings_contract.py tests/config` |
| `Core/application/rag/webui_retrieval_settings.py` | Remove when retrieval settings live behind a typed app-settings service. | `pytest tests/application tests/api/test_http_endpoints.py` |
| `Core/infrastructure/qdrant/collection_names.py` | Remove when all collection listing goes through `RagRuntime`/RagService HTTP. | `pytest tests/rag_service tests/api` |
| `CoreModules/LlmProxy/*` wire-format | Not a cleanup target; retire individual paths only through a compatibility deprecation. | `pytest tests/llm_proxy --maxfail=1` |
| `extensions/bundled/*` | Keep mirrors small; refresh from canonical extension releases when bundled payloads drift. | Extension runtime tests and security audit |

## System Map

```text
CoreUI (RAG Tests / Notifications / Builds)
  -> Core/api/http/webui_routes.py (+ webui_*_routes.py splits)
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

- Phases 1–4 removed root `api/`, `modules/`, and `prompts/` runtime folders.
- Phase 5 documents remaining intentional tails under `Core/`, `Core/modules/`,
  and `CoreModules/` (see table above).

Risk: startup-critical code can become invisible ownership debt if it returns
to the repository root without an allowlist entry.

## A) Configuration/authority overlap

- Multiple config sources for similar behavior:
  - `proxy_settings` JSON blob,
  - dedicated `app_settings` fields,
  - yaml/env fallback.
- Documented precedence: [`config/CONFIG_AUTHORITY.md`](../config/CONFIG_AUTHORITY.md),
  env index: [`config/ENV_REFERENCE.md`](../config/ENV_REFERENCE.md).
- Main files:
  - `Core/api/http/webui_settings_routes.py`, `webui_rag_routes.py`
  - `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py`
  - `Core/api/http/llm_proxy_wiring.py`

Risk: hidden runtime divergence (mitigated by precedence tests in `tests/config/`).

## B) WebUI routes composition

- `Core/api/http/webui_routes.py` is the composition root (~170 lines): blueprint bootstrap and
  `register_*` calls only.
- RAG trigger/default-model helpers live in `Core/application/rag/webui_retrieval_settings.py`.
- Qdrant collection listing lives in `Core/infrastructure/qdrant/collection_names.py`.
- Domain routes live in `webui_*_routes.py` (chat, rag, model tester, llm proxy,
  crawler, docker, extensions, observability, prompts, sessions, settings, performance,
  testing, provider helpers module).

Risk: low after route splits; regressions show up in `pytest tests/api tests/webui`.

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
- Application code uses `get_default_*` config getters; `get_ollama_*` names
  remain in the config layer for env/YAML compatibility only (guardrail:
  `tests/application/test_ollama_migration_guardrails.py`).

Guardrail: `tests/application/test_ollama_migration_guardrails.py` rejects any
`from infrastructure.ollama` import in core trees.

## D) Retrieval mode compatibility

- Named dense + hybrid only in `QdrantRagRepository` (unnamed single-vector collections rejected).
- `external_docs_rag` search adapter delegates to the same repository (no duplicate HTTP search path).
- Documented: [`CoreModules/RagService/docs/QDRANT_VECTOR_MODES.md`](../CoreModules/RagService/docs/QDRANT_VECTOR_MODES.md).
- Main file: `CoreModules/RagService/rag_service/infrastructure/qdrant_repository.py`

Risk: hybrid vs dense-only mismatch; guarded by `tests/rag_service/test_qdrant_vector_modes.py`.

## E) Service control split

- WebUI-level Qdrant actions now delegate to RagRuntime; extension-owned
  services use DockerManager host capabilities.
- Main files:
  - `Core/api/http/service_control.py`
  - `CoreModules/RagService/rag_service/runtime.py`

Risk: keep Qdrant status/ports aligned between WebUI and RagRuntime.

## F) UI integration legacy tails (mostly reduced)

- RAG run open from notifications uses App state (`pendingRagRunOpenId`), not window events.
- Model Tester → RAG tab pipeline trace uses `sessionStorage` only (no `CustomEvent` bridge).
- Main files:
  - `CoreModules/CoreUI/src/App.jsx`
  - `CoreModules/CoreUI/src/components/NotificationCenterShell.jsx`
  - `CoreModules/CoreUI/src/components/ragTab/helpers.js`

Risk: low; trace mirror refreshes on Rag tab mount and `visibilitychange`.

## Keep vs Remove

Keep (intentional compatibility):
- `/v1/chat/completions`, `/v1/messages`, and `/v1/responses`.
- OpenAI/provider message, tool, and vision wire-format mapping used by `/v1`.
- Provider runtime and extension action contracts.

Remove (technical legacy):
- core raw Ollama-compatible route ownership and direct `localhost:11434` fallbacks.
- dead compatibility wrappers around stable internal contracts (removed: `config.rag_prompts`, `rag_repository_impl`).
- global UI shims and implicit state globals.
- route-layer orchestration that belongs in application services.

## Suggested Sequence

1. ~~Extract RAG Tests backend from `webui_routes.py`.~~ (split into `rag_tests_routes.py`)
2. ~~Lock config authority table and enforce in code.~~ (`CONFIG_AUTHORITY.md`, `get_default_*`, guardrails)
3. ~~Reduce Qdrant compatibility branches.~~ (canonical `QdrantRagRepository`; adapter delegates)
4. ~~Normalize UI action dispatch to state-only flow.~~ (RAG run + trace mirror)
5. Review compatibility endpoints and either bless or deprecate (`ollama_compat`, legacy tool stream documented as intentional).
