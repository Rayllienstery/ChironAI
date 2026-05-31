# Legacy Map

Updated: 2026-04-19

## System Map

```text
CoreUI (RAG Tests / Notifications / Builds)
  -> api/http/webui_routes.py
      -> application/rag_tests/*
      -> application/rag/params.py
      -> CoreModules/RagService/rag_service/*
      -> RagRuntime + DockerManager (Qdrant service control)
  -> CoreModules/LlmProxy/llm_proxy/*
      -> OpenAI/Anthropic compatibility surface
      -> same RAG context build path
```

## Legacy Clusters

## A) Configuration/authority overlap

- Multiple config sources for similar behavior:
  - `proxy_settings` JSON blob,
  - dedicated `app_settings` fields,
  - yaml/env fallback.
- Main files:
  - `api/http/webui_routes.py`
  - `CoreModules/LlmProxy/llm_proxy/chat_completions.py`
  - `api/http/llm_proxy_wiring.py`

Risk: hidden runtime divergence.

## B) WebUI routes monolith

- `api/http/webui_routes.py` still mixes:
  - proxy/tester endpoints,
  - RAG tests orchestration,
  - service lifecycle control,
  - crawler/indexer/web interaction helpers.

Risk: coupling, regression risk, hard ownership.

## C) Protocol compatibility surface

- Intentional legacy-compatible endpoints and request shapes:
  - OpenAI legacy completions (`/v1/completions`)
  - prompt/suffix normalization
  - raw Ollama-compatible `/api/tags`, `/api/show`, `/api/generate`, and `/api/chat`
- Main files:
  - `CoreModules/LlmProxy/llm_proxy/v1_blueprint.py`
  - `CoreModules/LlmProxy/llm_proxy/completions_generate.py`
  - `CoreModules/LlmProxy/llm_proxy/ollama_upstream.py`
  - `extensions/bundled/ollama-provider/backend/provider.py`

Risk: complexity if undocumented; low risk if treated as explicit contract.

Current ownership: these public routes remain on the compatibility blueprint so
existing clients keep their base URLs and status shapes. Their first-choice
implementation delegates to `ollama-provider` through `LLMRuntime` operation
`raw_ollama`; direct upstream HTTP remains as a fallback when the extension
runtime is still loading or unavailable.

## G) Ollama compatibility adapters

- Root `infrastructure/ollama/*` and duplicate RagService
  `rag_service.infrastructure.ollama_*` modules are retained as temporary
  compatibility boundaries for public proxy helpers, standalone tests, and
  fallback runtime paths.
- New provider behavior belongs in the `chironai-extension-ollama-provider`
  repository first. `extensions/bundled/ollama-provider` is a trusted
  bootstrap/offline mirror only.
- New app call sites should use `LLMRuntime`, provider catalog/actions, or a
  clearly documented compatibility adapter.

Guardrail: `tests/application/test_ollama_migration_guardrails.py` rejects new
direct `infrastructure.ollama` imports unless the file is explicitly allowlisted
as a compatibility or test boundary.

## D) Retrieval mode compatibility

- Dense-only + hybrid + named dense compatibility in Qdrant repositories.
- Main files:
  - `CoreModules/RagService/rag_service/infrastructure/qdrant_repository.py`
  - `infrastructure/qdrant/rag_repository_impl.py`

Risk: subtle retrieval behavior differences.

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
- `/v1/completions` if needed by existing clients (document + test).
- prompt/suffix mapping for old clients, if still in active use.
- raw Ollama-compatible `/api/*` passthrough routes for clients that use this
  app as an Ollama base URL.

Remove (technical legacy):
- dead compatibility wrappers around stable internal contracts.
- global UI shims and implicit state globals.
- route-layer orchestration that belongs in application services.

## Suggested Sequence

1. Extract RAG Tests backend from `webui_routes.py`.
2. Lock config authority table and enforce in code.
3. Reduce Qdrant compatibility branches.
4. Normalize UI action dispatch to state-only flow.
5. Review compatibility endpoints and either bless or deprecate.
