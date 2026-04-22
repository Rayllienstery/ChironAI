# Legacy Map

Updated: 2026-04-19

## System Map

```text
CoreUI (RAG Tests / Notifications / Builds)
  -> api/http/webui_routes.py
      -> application/rag_tests/*
      -> application/rag/params.py
      -> CoreModules/RagService/rag_service/*
      -> ServiceStarter (service control)
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
  - inline `/api/generate` bridge
- Main files:
  - `CoreModules/LlmProxy/llm_proxy/v1_blueprint.py`
  - `CoreModules/LlmProxy/llm_proxy/completions_generate.py`
  - `CoreModules/LlmProxy/llm_proxy/chat_completions.py`

Risk: complexity if undocumented; low risk if treated as explicit contract.

## D) Retrieval mode compatibility

- Dense-only + hybrid + named dense compatibility in Qdrant repositories.
- Main files:
  - `CoreModules/RagService/rag_service/infrastructure/qdrant_repository.py`
  - `infrastructure/qdrant/rag_repository_impl.py`

Risk: subtle retrieval behavior differences.

## E) Service control split

- ServiceStarter module + WebUI-level orchestration overlap.
- Main files:
  - `CoreModules/ServiceStarter/*`
  - `api/http/webui_routes.py`

Risk: operational ambiguity (status/ports/startup source of truth).

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
